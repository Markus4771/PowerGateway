#!/usr/bin/env python3
"""No-IP-DDNS-Konfiguration, Update und Diagnose."""
from __future__ import annotations

import base64
import json
import os
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
CONFIG_PATH = DATA_DIR / "noip_config.json"
STATUS_PATH = DATA_DIR / "noip_status.json"
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "hostname": "",
    "username": "",
    "password": "",
    "update_url": "https://dynupdate.no-ip.com/nic/update",
    "public_ip_url": "https://api.ipify.org",
    "interval_minutes": 10,
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


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or load_config())
    config["password"] = ""
    config["has_password"] = bool((config or load_config()).get("password"))
    return config


def validate_config(supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige No-IP-Konfiguration")
    current = load_config()
    config = dict(current)
    config.update(supplied)
    if not str(supplied.get("password", "")).strip():
        config["password"] = current.get("password", "")
    config["enabled"] = bool(config.get("enabled"))
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


def update(config: dict[str, Any] | None = None, address: str | None = None) -> dict[str, Any]:
    config = config or load_config()
    if not config.get("enabled"):
        result = {"ok": False, "status": "disabled", "message": "No-IP ist deaktiviert"}
        _atomic(STATUS_PATH, result, 0o640)
        return result
    ip = address or public_ip(config)
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
        result = {"ok": False, "status": "http_error", "message": body or str(exc), "public_ip": ip}
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
    result = {"ok": ok, "status": code, "message": messages.get(code, body or "Unbekannte No-IP-Antwort"), "response": body, "public_ip": ip, "hostname": config["hostname"]}
    _atomic(STATUS_PATH, result, 0o640)
    return result


if __name__ == "__main__":
    print(json.dumps(update(), ensure_ascii=False))
