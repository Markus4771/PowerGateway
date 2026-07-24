#!/usr/bin/env python3
"""No-IP-DDNS-Konfiguration, intelligente Aktualisierung und Diagnose."""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
CONFIG_PATH = DATA_DIR / "noip_config.json"
STATUS_PATH = DATA_DIR / "noip_status.json"
TUNNEL_SERVICE = "powergateway-ha-tunnel.service"
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "hostname": "",
    "username": "",
    "password": "",
    "update_url": "https://dynupdate.no-ip.com/nic/update",
    "public_ip_url": "https://api.ipify.org",
    "interval_minutes": 10,
    "restart_ssh_on_ip_change": True,
}


def _atomic(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            config.update(stored)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return config


def load_status() -> dict[str, Any]:
    try:
        value = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(config or load_config())
    has_password = bool(source.get("password"))
    source["password"] = ""
    source["has_password"] = has_password
    return source


def validate_config(supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige No-IP-Konfiguration")
    current = load_config()
    config = dict(current)
    config.update(supplied)
    if not str(supplied.get("password", "")).strip():
        config["password"] = current.get("password", "")
    config["enabled"] = bool(config.get("enabled"))
    config["restart_ssh_on_ip_change"] = bool(config.get("restart_ssh_on_ip_change", True))
    for field in ("hostname", "username", "password", "update_url", "public_ip_url"):
        config[field] = str(config.get(field, "")).strip()
    try:
        interval = int(config.get("interval_minutes", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("Das No-IP-Intervall ist ungültig") from exc
    if interval < 5 or interval > 1440:
        raise ValueError("Das No-IP-Intervall muss zwischen 5 und 1440 Minuten liegen")
    config["interval_minutes"] = interval
    if config["enabled"] and (not config["hostname"] or not config["username"] or not config["password"]):
        raise ValueError("Für No-IP fehlen Hostname, Benutzername oder Passwort")
    return config


def save_config(supplied: dict[str, Any]) -> dict[str, Any]:
    config = validate_config(supplied)
    _atomic(CONFIG_PATH, config)
    return config


def public_ip(config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    request = urllib.request.Request(str(config["public_ip_url"]), headers={"User-Agent": "PowerGateway/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        value = response.read(128).decode("ascii", errors="replace").strip()
    socket.inet_pton(socket.AF_INET, value)
    return value


def _restart_ssh_tunnel() -> dict[str, Any]:
    try:
        state = subprocess.run(
            ["/usr/bin/systemctl", "is-active", TUNNEL_SERVICE],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if state.stdout.strip() != "active":
            return {"requested": False, "ok": True, "message": "SSH-Tunnel ist nicht aktiv"}
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", TUNNEL_SERVICE],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return {
            "requested": True,
            "ok": result.returncode == 0,
            "message": result.stderr.strip() or result.stdout.strip() or "SSH-Tunnel wurde neu gestartet",
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"requested": True, "ok": False, "message": str(exc)}


def diagnostics(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    checks: dict[str, Any] = {}
    try:
        ip = public_ip(config)
        checks["public_ip"] = {"ok": True, "message": ip, "value": ip}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        checks["public_ip"] = {"ok": False, "message": str(exc)}
    try:
        resolved = socket.gethostbyname(str(config.get("hostname", ""))) if config.get("hostname") else ""
        checks["hostname_dns"] = {"ok": bool(resolved), "message": resolved or "Kein Hostname konfiguriert", "value": resolved}
    except OSError as exc:
        checks["hostname_dns"] = {"ok": False, "message": str(exc)}
    status = load_status()
    checks["last_update"] = {
        "ok": bool(status.get("ok")),
        "message": str(status.get("message", "Noch kein Update ausgeführt")),
        "status": status.get("status", "unknown"),
    }
    return {"ok": all(item.get("ok", False) for item in checks.values()), "checks": checks, "status": status}


def update(config: dict[str, Any] | None = None, address: str | None = None, force: bool = False) -> dict[str, Any]:
    config = validate_config(config or load_config())
    now = int(time.time())
    previous = load_status()
    interval_seconds = int(config["interval_minutes"]) * 60
    next_due = int(previous.get("last_attempt_at", 0)) + interval_seconds

    if not config.get("enabled"):
        result = {"ok": False, "status": "disabled", "message": "No-IP ist deaktiviert", "last_attempt_at": now}
        _atomic(STATUS_PATH, result, 0o640)
        return result
    if not force and previous.get("last_attempt_at") and now < next_due:
        result = dict(previous)
        result.update({"status": "not_due", "message": "Das konfigurierte Update-Intervall ist noch nicht erreicht", "next_update_at": next_due})
        return result

    try:
        ip = address or public_ip(config)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        result = {
            "ok": False,
            "status": "public_ip_error",
            "message": str(exc),
            "last_attempt_at": now,
            "next_update_at": now + interval_seconds,
        }
        _atomic(STATUS_PATH, result, 0o640)
        return result

    old_ip = str(previous.get("public_ip", ""))
    changed = bool(old_ip and old_ip != ip)
    if not force and old_ip == ip and previous.get("ok"):
        result = dict(previous)
        result.update({
            "ok": True,
            "status": "unchanged",
            "message": "Öffentliche IP ist unverändert; kein No-IP-Update erforderlich",
            "public_ip": ip,
            "ip_changed": False,
            "last_attempt_at": now,
            "next_update_at": now + interval_seconds,
        })
        _atomic(STATUS_PATH, result, 0o640)
        return result

    query = urllib.parse.urlencode({"hostname": config["hostname"], "myip": ip})
    token = base64.b64encode(f"{config['username']}:{config['password']}".encode()).decode()
    request = urllib.request.Request(
        f"{config['update_url']}?{query}",
        headers={"Authorization": f"Basic {token}", "User-Agent": "PowerGateway/1.0 admin@localhost"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(512).decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace").strip()
        result = {
            "ok": False,
            "status": "http_error",
            "message": body or str(exc),
            "public_ip": ip,
            "ip_changed": changed,
            "last_attempt_at": now,
            "next_update_at": now + interval_seconds,
        }
        _atomic(STATUS_PATH, result, 0o640)
        return result
    except urllib.error.URLError as exc:
        result = {
            "ok": False,
            "status": "network_error",
            "message": str(exc),
            "public_ip": ip,
            "ip_changed": changed,
            "last_attempt_at": now,
            "next_update_at": now + interval_seconds,
        }
        _atomic(STATUS_PATH, result, 0o640)
        return result

    code = body.split()[0].lower() if body else "empty"
    ok = code in {"good", "nochg"}
    messages = {
        "good": "Hostname wurde aktualisiert",
        "nochg": "Hostname war bereits aktuell",
        "badauth": "No-IP-Anmeldung fehlgeschlagen",
        "nohost": "Der No-IP-Hostname wurde nicht gefunden",
        "abuse": "Der No-IP-Hostname ist gesperrt",
        "911": "No-IP meldet eine vorübergehende Störung",
    }
    tunnel = {"requested": False, "ok": True, "message": "Kein Neustart erforderlich"}
    if ok and changed and config.get("restart_ssh_on_ip_change", True):
        tunnel = _restart_ssh_tunnel()
    result = {
        "ok": ok,
        "status": code,
        "message": messages.get(code, body or "Unbekannte No-IP-Antwort"),
        "response": body,
        "public_ip": ip,
        "previous_public_ip": old_ip,
        "ip_changed": changed,
        "hostname": config["hostname"],
        "last_attempt_at": now,
        "last_success_at": now if ok else previous.get("last_success_at"),
        "next_update_at": now + interval_seconds,
        "ssh_tunnel": tunnel,
    }
    _atomic(STATUS_PATH, result, 0o640)
    return result


if __name__ == "__main__":
    print(json.dumps(update(), ensure_ascii=False))
