#!/usr/bin/env python3
"""No-IP-DDNS mit Dual Stack, Multi-WAN, Fallback-Diensten und Diagnose."""
from __future__ import annotations

import base64
import ipaddress
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
HISTORY_PATH = DATA_DIR / "noip_history.json"
NETWORK_CONFIG_PATH = DATA_DIR / "network_config.json"
NETWORK_STATUS_PATH = DATA_DIR / "network_status.json"
SSH_SERVICE = "powergateway-ha-tunnel.service"
WIREGUARD_SERVICE = "wg-quick@wg0.service"
HISTORY_LIMIT = 100

IPV4_SERVICES = [
    "https://ip1.dynupdate.no-ip.com/",
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
]
IPV6_SERVICES = [
    "https://ip1.dynupdate6.no-ip.com/",
    "https://api64.ipify.org",
    "https://ifconfig.me/ip",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "hostname": "",
    "username": "",
    "password": "",
    "update_url": "https://dynupdate.no-ip.com/nic/update",
    "public_ip_url": IPV4_SERVICES[0],
    "public_ipv6_url": IPV6_SERVICES[0],
    "interval_minutes": 10,
    "ipv4_enabled": True,
    "ipv6_enabled": False,
    "restart_ssh_on_ip_change": True,
    "restart_wireguard_on_ip_change": False,
    "interface_mode": "active",
    "interface": "",
}


def _atomic(path: Path, value: Any, mode: int = 0o600) -> None:
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


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    stored = _read_json(CONFIG_PATH, {})
    if isinstance(stored, dict):
        config.update(stored)
    return config


def load_status() -> dict[str, Any]:
    value = _read_json(STATUS_PATH, {})
    return value if isinstance(value, dict) else {}


def load_history(limit: int = 50) -> list[dict[str, Any]]:
    value = _read_json(HISTORY_PATH, [])
    rows = value if isinstance(value, list) else []
    return [row for row in rows[-max(1, min(limit, HISTORY_LIMIT)):] if isinstance(row, dict)]


def _append_history(result: dict[str, Any]) -> None:
    history = load_history(HISTORY_LIMIT)
    history.append({
        "timestamp": int(time.time()),
        "ok": bool(result.get("ok")),
        "status": result.get("status", "unknown"),
        "message": result.get("message", ""),
        "interface": result.get("interface"),
        "public_ipv4": result.get("public_ipv4"),
        "public_ipv6": result.get("public_ipv6"),
        "ipv4_service": result.get("ipv4_service"),
        "ipv6_service": result.get("ipv6_service"),
        "ipv4_changed": bool(result.get("ipv4_changed")),
        "ipv6_changed": bool(result.get("ipv6_changed")),
    })
    _atomic(HISTORY_PATH, history[-HISTORY_LIMIT:], 0o640)


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(config or load_config())
    source["has_password"] = bool(source.get("password"))
    source["password"] = ""
    return source


def validate_config(supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige No-IP-Konfiguration")
    current = load_config()
    config = dict(current)
    config.update(supplied)
    if not str(supplied.get("password", "")).strip():
        config["password"] = current.get("password", "")
    for field in ("enabled", "ipv4_enabled", "ipv6_enabled", "restart_ssh_on_ip_change", "restart_wireguard_on_ip_change"):
        config[field] = bool(config.get(field))
    for field in ("hostname", "username", "password", "update_url", "public_ip_url", "public_ipv6_url", "interface", "interface_mode"):
        config[field] = str(config.get(field, "")).strip()
    if config["interface_mode"] not in {"active", "auto", "lan", "wifi", "lte", "custom"}:
        raise ValueError("Ungültige DDNS-Schnittstellenauswahl")
    try:
        interval = int(config.get("interval_minutes", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("Das No-IP-Intervall ist ungültig") from exc
    if interval < 5 or interval > 1440:
        raise ValueError("Das No-IP-Intervall muss zwischen 5 und 1440 Minuten liegen")
    config["interval_minutes"] = interval
    if config["enabled"] and not (config["ipv4_enabled"] or config["ipv6_enabled"]):
        raise ValueError("Mindestens IPv4 oder IPv6 muss aktiviert sein")
    if config["enabled"] and (not config["hostname"] or not config["username"] or not config["password"]):
        raise ValueError("Für No-IP fehlen Hostname, Benutzername oder Passwort")
    return config


def save_config(supplied: dict[str, Any]) -> dict[str, Any]:
    config = validate_config(supplied)
    _atomic(CONFIG_PATH, config)
    return config


def _interface_from_kind(kind: str) -> str:
    status = _read_json(NETWORK_STATUS_PATH, {})
    link = status.get(kind, {}) if isinstance(status, dict) else {}
    if isinstance(link, dict) and link.get("interface"):
        return str(link["interface"])
    defaults = {"lan": "eth0", "wifi": "wlan0", "lte": "eth1"}
    return defaults.get(kind, "")


def selected_interface(config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    mode = str(config.get("interface_mode", "active"))
    if mode == "custom":
        return str(config.get("interface", "")).strip()
    if mode in {"lan", "wifi", "lte"}:
        return _interface_from_kind(mode)
    if mode == "active":
        status = _read_json(NETWORK_STATUS_PATH, {})
        active = str(status.get("active", "")) if isinstance(status, dict) else ""
        if active in {"lan", "wifi", "lte"}:
            return _interface_from_kind(active)
        network = _read_json(NETWORK_CONFIG_PATH, {})
        preferred = str(network.get("preferred_gateway", "auto")) if isinstance(network, dict) else "auto"
        if preferred in {"lan", "wifi", "lte"}:
            return _interface_from_kind(preferred)
    return ""


def _curl_address(url: str, family: int, interface: str = "", timeout: int = 10) -> tuple[str, float]:
    command = ["/usr/bin/curl", "--silent", "--show-error", "--fail", "--max-time", str(timeout)]
    command.append("-4" if family == socket.AF_INET else "-6")
    if interface:
        command.extend(["--interface", interface])
    command.append(url)
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 3, check=False)
    elapsed = round((time.monotonic() - started) * 1000)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or result.stdout.strip() or f"curl Fehler {result.returncode}")
    value = result.stdout.strip()
    ip = ipaddress.ip_address(value)
    expected = 4 if family == socket.AF_INET else 6
    if ip.version != expected:
        raise ValueError(f"Unerwartete IP-Version: {value}")
    return value, elapsed


def _service_list(config: dict[str, Any], family: int) -> list[str]:
    configured = str(config.get("public_ip_url" if family == socket.AF_INET else "public_ipv6_url", "")).strip()
    defaults = IPV4_SERVICES if family == socket.AF_INET else IPV6_SERVICES
    return list(dict.fromkeys([configured, *defaults])) if configured else list(defaults)


def detect_public_address(config: dict[str, Any] | None, family: int, interface: str | None = None) -> dict[str, Any]:
    config = config or load_config()
    interface = selected_interface(config) if interface is None else interface
    attempts: list[dict[str, Any]] = []
    for url in _service_list(config, family):
        try:
            address, latency = _curl_address(url, family, interface)
            return {"ok": True, "address": address, "service": url, "latency_ms": latency, "interface": interface or "Standardroute", "attempts": attempts}
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            attempts.append({"service": url, "error": str(exc)})
    label = "IPv4" if family == socket.AF_INET else "IPv6"
    raise OSError(f"{label} konnte über keine IP-Erkennung ermittelt werden: " + "; ".join(f"{x['service']}: {x['error']}" for x in attempts))


def public_ip(config: dict[str, Any] | None = None) -> str:
    return str(detect_public_address(config, socket.AF_INET)["address"])


def public_ipv6(config: dict[str, Any] | None = None) -> str:
    return str(detect_public_address(config, socket.AF_INET6)["address"])


def _restart_service(service: str, label: str) -> dict[str, Any]:
    try:
        state = subprocess.run(["/usr/bin/systemctl", "is-active", service], capture_output=True, text=True, timeout=5, check=False)
        if state.stdout.strip() != "active":
            return {"requested": False, "ok": True, "message": f"{label} ist nicht aktiv"}
        result = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "restart", service], capture_output=True, text=True, timeout=30, check=False)
        return {"requested": True, "ok": result.returncode == 0, "message": result.stderr.strip() or result.stdout.strip() or f"{label} wurde neu gestartet"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"requested": True, "ok": False, "message": str(exc)}


def _resolve(hostname: str, family: int) -> list[str]:
    if not hostname:
        return []
    return sorted({entry[4][0] for entry in socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)})


def multiwan_diagnostics(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    rows: dict[str, Any] = {}
    for kind in ("lan", "wifi", "lte"):
        interface = _interface_from_kind(kind)
        if not Path("/sys/class/net", interface).exists():
            rows[kind] = {"ok": False, "interface": interface, "message": "Schnittstelle nicht vorhanden"}
            continue
        try:
            result = detect_public_address(config, socket.AF_INET, interface)
            rows[kind] = {"ok": True, **result}
        except OSError as exc:
            rows[kind] = {"ok": False, "interface": interface, "message": str(exc)}
    return rows


def diagnostics(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    checks: dict[str, Any] = {}
    interface = selected_interface(config)
    if config.get("ipv4_enabled", True):
        try:
            result = detect_public_address(config, socket.AF_INET, interface)
            checks["public_ipv4"] = {"ok": True, "message": result["address"], **result}
        except OSError as exc:
            checks["public_ipv4"] = {"ok": False, "message": str(exc), "interface": interface}
    if config.get("ipv6_enabled"):
        try:
            result = detect_public_address(config, socket.AF_INET6, interface)
            checks["public_ipv6"] = {"ok": True, "message": result["address"], **result}
        except OSError as exc:
            checks["public_ipv6"] = {"ok": False, "message": str(exc), "interface": interface}
    try:
        ipv4 = _resolve(str(config.get("hostname", "")), socket.AF_INET)
        checks["dns_a"] = {"ok": bool(ipv4) if config.get("ipv4_enabled", True) else True, "message": ", ".join(ipv4) or "Kein A-Record gefunden", "values": ipv4}
    except OSError as exc:
        checks["dns_a"] = {"ok": False, "message": str(exc)}
    try:
        ipv6 = _resolve(str(config.get("hostname", "")), socket.AF_INET6)
        checks["dns_aaaa"] = {"ok": bool(ipv6) if config.get("ipv6_enabled") else True, "message": ", ".join(ipv6) or "Kein AAAA-Record gefunden", "values": ipv6}
    except OSError as exc:
        checks["dns_aaaa"] = {"ok": not config.get("ipv6_enabled"), "message": str(exc)}
    status = load_status()
    checks["last_update"] = {"ok": bool(status.get("ok")), "message": str(status.get("message", "Noch kein Update ausgeführt")), "status": status.get("status", "unknown")}
    return {"ok": all(item.get("ok", False) for item in checks.values()), "selected_interface": interface or "Standardroute", "checks": checks, "multiwan": multiwan_diagnostics(config), "status": status, "history": load_history(20)}


def _finish(result: dict[str, Any], save_status: bool = True) -> dict[str, Any]:
    if save_status:
        _atomic(STATUS_PATH, result, 0o640)
        _append_history(result)
    return result


def _noip_request(config: dict[str, Any], addresses: list[str], interface: str) -> tuple[int, str]:
    query = urllib.parse.urlencode({"hostname": config["hostname"], "myip": ",".join(addresses)})
    url = f"{config['update_url']}?{query}"
    command = ["/usr/bin/curl", "--silent", "--show-error", "--max-time", "20", "--user", f"{config['username']}:{config['password']}", "--user-agent", "PowerGateway DDNS/Linux-0.9 maintainer@localhost"]
    if interface:
        command.extend(["--interface", interface])
    command.append(url)
    result = subprocess.run(command, capture_output=True, text=True, timeout=25, check=False)
    return result.returncode, result.stdout.strip() or result.stderr.strip()


def update(config: dict[str, Any] | None = None, address: str | None = None, force: bool = False) -> dict[str, Any]:
    config = validate_config(config or load_config())
    now = int(time.time())
    previous = load_status()
    interval_seconds = int(config["interval_minutes"]) * 60
    next_due = int(previous.get("last_attempt_at", 0)) + interval_seconds
    interface = selected_interface(config)
    if not config.get("enabled"):
        return _finish({"ok": False, "status": "disabled", "message": "No-IP ist deaktiviert", "interface": interface or "Standardroute", "last_attempt_at": now})
    if not force and previous.get("last_attempt_at") and now < next_due:
        result = dict(previous)
        result.update({"status": "not_due", "message": "Das konfigurierte Update-Intervall ist noch nicht erreicht", "next_update_at": next_due})
        return result

    ipv4 = ipv6 = None
    ipv4_meta: dict[str, Any] = {}
    ipv6_meta: dict[str, Any] = {}
    errors: list[str] = []
    if config.get("ipv4_enabled", True):
        try:
            ipv4_meta = {"address": address, "service": "vorgegeben", "interface": interface} if address else detect_public_address(config, socket.AF_INET, interface)
            ipv4 = str(ipv4_meta["address"])
        except OSError as exc:
            errors.append(f"IPv4: {exc}")
    if config.get("ipv6_enabled"):
        try:
            ipv6_meta = detect_public_address(config, socket.AF_INET6, interface)
            ipv6 = str(ipv6_meta["address"])
        except OSError as exc:
            errors.append(f"IPv6: {exc}")
    if errors:
        return _finish({"ok": False, "status": "public_ip_error", "message": "; ".join(errors), "interface": interface or "Standardroute", "last_attempt_at": now, "next_update_at": now + interval_seconds})

    old4 = str(previous.get("public_ipv4") or previous.get("public_ip") or "")
    old6 = str(previous.get("public_ipv6") or "")
    changed4 = bool(ipv4 and old4 and old4 != ipv4)
    changed6 = bool(ipv6 and old6 and old6 != ipv6)
    unchanged = (not ipv4 or old4 == ipv4) and (not ipv6 or old6 == ipv6)
    if not force and unchanged and previous.get("ok"):
        result = dict(previous)
        result.update({"ok": True, "status": "unchanged", "message": "Öffentliche IP-Adressen sind unverändert", "interface": interface or "Standardroute", "public_ipv4": ipv4, "public_ipv6": ipv6, "ipv4_changed": False, "ipv6_changed": False, "last_attempt_at": now, "next_update_at": now + interval_seconds})
        return _finish(result)

    returncode, body = _noip_request(config, [value for value in (ipv4, ipv6) if value], interface)
    if returncode != 0:
        return _finish({"ok": False, "status": "network_error", "message": body or f"curl Fehler {returncode}", "interface": interface or "Standardroute", "public_ipv4": ipv4, "public_ipv6": ipv6, "last_attempt_at": now, "next_update_at": now + interval_seconds})

    code = body.split()[0].lower() if body else "empty"
    ok = code in {"good", "nochg"}
    messages = {"good": "Hostname wurde aktualisiert", "nochg": "Hostname war bereits aktuell", "badauth": "No-IP-Anmeldung fehlgeschlagen", "badagent": "No-IP hat den Update-Client abgelehnt", "nohost": "Der No-IP-Hostname wurde nicht gefunden", "abuse": "Der No-IP-Hostname ist gesperrt", "911": "No-IP meldet eine vorübergehende Störung"}
    any_changed = changed4 or changed6
    ssh = {"requested": False, "ok": True, "message": "Kein Neustart erforderlich"}
    wireguard = {"requested": False, "ok": True, "message": "Kein Neustart erforderlich"}
    if ok and any_changed and config.get("restart_ssh_on_ip_change", True):
        ssh = _restart_service(SSH_SERVICE, "SSH-Tunnel")
    if ok and any_changed and config.get("restart_wireguard_on_ip_change"):
        wireguard = _restart_service(WIREGUARD_SERVICE, "WireGuard")
    result = {
        "ok": ok,
        "status": code,
        "message": messages.get(code, body or "Unbekannte No-IP-Antwort"),
        "response": body,
        "interface": interface or "Standardroute",
        "public_ipv4": ipv4,
        "previous_public_ipv4": old4,
        "ipv4_service": ipv4_meta.get("service"),
        "ipv4_latency_ms": ipv4_meta.get("latency_ms"),
        "public_ipv6": ipv6,
        "previous_public_ipv6": old6,
        "ipv6_service": ipv6_meta.get("service"),
        "ipv6_latency_ms": ipv6_meta.get("latency_ms"),
        "ipv4_changed": changed4,
        "ipv6_changed": changed6,
        "hostname": config["hostname"],
        "last_attempt_at": now,
        "last_success_at": now if ok else previous.get("last_success_at"),
        "next_update_at": now + interval_seconds,
        "ssh_tunnel": ssh,
        "wireguard": wireguard,
    }
    return _finish(result)


if __name__ == "__main__":
    print(json.dumps(update(), ensure_ascii=False))
