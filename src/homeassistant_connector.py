#!/usr/bin/env python3
"""Konfiguration und Diagnose der Verbindung zu einem einzelnen Home Assistant."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
CONFIG_PATH = DATA_DIR / "homeassistant_connector.json"
STATUS_PATH = DATA_DIR / "homeassistant_connector_status.json"
MODES = {"direct_mqtt", "wireguard_mqtt", "ssh_mqtt", "reverse_ssh_mqtt"}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "direct_mqtt",
    "ha_host": "",
    "ha_port": 8123,
    "mqtt_host": "",
    "mqtt_port": 1883,
    "mqtt_tls": False,
    "noip_hostname": "",
    "ssh_host": "",
    "ssh_port": 22,
    "ssh_user": "",
    "identity_file": "/var/lib/powergateway/.ssh/id_ed25519",
    "known_hosts_file": "/var/lib/powergateway/.ssh/known_hosts",
    "local_mqtt_port": 18830,
    "remote_mqtt_host": "127.0.0.1",
    "remote_mqtt_port": 1883,
    "reverse_bind_host": "127.0.0.1",
    "reverse_bind_port": 18830,
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
    value = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            value.update(stored)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return value


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(config or load_config())


def _port(value: Any, label: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} ist ungültig") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{label} muss zwischen 1 und 65535 liegen")
    return port


def validate_config(supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige Home-Assistant-Konfiguration")
    current = load_config()
    config = dict(current)
    config.update(supplied)
    mode = str(config.get("mode", "direct_mqtt")).strip()
    if mode not in MODES:
        raise ValueError("Ungültige Verbindungsart")
    config["mode"] = mode
    config["enabled"] = bool(config.get("enabled"))
    for field in ("ha_host", "mqtt_host", "noip_hostname", "ssh_host", "ssh_user", "identity_file", "known_hosts_file", "remote_mqtt_host", "reverse_bind_host"):
        config[field] = str(config.get(field, "")).strip()
    config["ha_port"] = _port(config.get("ha_port", 8123), "Home-Assistant-Port")
    config["mqtt_port"] = _port(config.get("mqtt_port", 1883), "MQTT-Port")
    config["ssh_port"] = _port(config.get("ssh_port", 22), "SSH-Port")
    config["local_mqtt_port"] = _port(config.get("local_mqtt_port", 18830), "Lokaler Tunnel-Port")
    config["remote_mqtt_port"] = _port(config.get("remote_mqtt_port", 1883), "Entfernter MQTT-Port")
    config["reverse_bind_port"] = _port(config.get("reverse_bind_port", 18830), "Reverse-Tunnel-Port")
    config["mqtt_tls"] = bool(config.get("mqtt_tls"))
    if config["enabled"] and mode in {"ssh_mqtt", "reverse_ssh_mqtt"}:
        if not config["ssh_host"] or not config["ssh_user"]:
            raise ValueError("Für den SSH-Tunnel fehlen SSH-Server oder Benutzer")
        if not config["identity_file"]:
            raise ValueError("Für den SSH-Tunnel fehlt die Schlüsseldatei")
    return config


def save_config(supplied: dict[str, Any]) -> dict[str, Any]:
    config = validate_config(supplied)
    _atomic(CONFIG_PATH, config)
    return config


def generate_ssh_key(identity_file: str | None = None) -> dict[str, str]:
    path = Path(identity_file or load_config()["identity_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.with_suffix(path.suffix + ".pub").exists():
        public = path.with_suffix(path.suffix + ".pub").read_text(encoding="utf-8").strip()
        return {"identity_file": str(path), "public_key": public, "created": False}
    if not shutil.which("ssh-keygen"):
        raise ValueError("ssh-keygen ist nicht installiert")
    result = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(path), "-C", "powergateway"], capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "SSH-Schlüssel konnte nicht erzeugt werden")
    os.chmod(path, 0o600)
    os.chmod(path.with_suffix(path.suffix + ".pub"), 0o644)
    return {"identity_file": str(path), "public_key": path.with_suffix(path.suffix + ".pub").read_text(encoding="utf-8").strip(), "created": True}


def _tcp(host: str, port: int, timeout: float = 4.0) -> dict[str, Any]:
    if not host:
        return {"ok": False, "message": "Kein Host konfiguriert"}
    try:
        started = __import__("time").monotonic()
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = round((__import__("time").monotonic() - started) * 1000)
        return {"ok": True, "message": f"Erreichbar ({elapsed} ms)", "latency_ms": elapsed}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def diagnostics(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config()
    mode = config.get("mode", "direct_mqtt")
    mqtt_host = config.get("mqtt_host", "")
    mqtt_port = int(config.get("mqtt_port", 1883))
    if mode == "ssh_mqtt":
        mqtt_host, mqtt_port = "127.0.0.1", int(config.get("local_mqtt_port", 18830))
    checks = {
        "home_assistant": _tcp(str(config.get("ha_host", "")), int(config.get("ha_port", 8123))),
        "mqtt": _tcp(str(mqtt_host), mqtt_port),
        "ssh": {"ok": True, "message": "Nicht erforderlich"},
        "wireguard": {"ok": True, "message": "Nicht erforderlich"},
    }
    if mode in {"ssh_mqtt", "reverse_ssh_mqtt"}:
        checks["ssh"] = _tcp(str(config.get("ssh_host", "")), int(config.get("ssh_port", 22)))
        checks["ssh_key"] = {"ok": Path(str(config.get("identity_file", ""))).is_file(), "message": "Schlüssel vorhanden" if Path(str(config.get("identity_file", ""))).is_file() else "Schlüssel fehlt"}
    if mode == "wireguard_mqtt":
        result = subprocess.run(["wg", "show"], capture_output=True, text=True, timeout=5, check=False) if shutil.which("wg") else None
        checks["wireguard"] = {"ok": bool(result and result.returncode == 0 and result.stdout.strip()), "message": "WireGuard-Tunnel aktiv" if result and result.returncode == 0 and result.stdout.strip() else "Kein aktiver WireGuard-Tunnel erkannt"}
    result = {"ok": all(item.get("ok", False) for item in checks.values()), "mode": mode, "checks": checks}
    _atomic(STATUS_PATH, result, 0o640)
    return result
