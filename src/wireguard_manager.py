#!/usr/bin/env python3
"""WireGuard-Konfiguration und Status für PowerGateway."""
from __future__ import annotations

import base64
import configparser
import ipaddress
import json
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA", "/var/lib/powergateway"))
CONFIG_PATH = DATA_DIR / "wireguard.json"
STATUS_PATH = DATA_DIR / "wireguard_status.json"
INTERFACE_RE = re.compile(r"^[a-zA-Z0-9_=+.-]{1,15}$")

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "interface": "wg0",
    "autostart": True,
    "address": "10.20.30.2/24",
    "dns": "",
    "mtu": 1420,
    "private_key": "",
    "public_key": "",
    "peer": {
        "name": "VPN-Gegenstelle",
        "public_key": "",
        "preshared_key": "",
        "endpoint": "",
        "allowed_ips": "0.0.0.0/0",
        "persistent_keepalive": 25,
    },
}


def atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
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
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    result = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in data.items() if isinstance(data, dict) else []:
        if key == "peer" and isinstance(value, dict):
            result["peer"].update(value)
        else:
            result[key] = value
    return result


def load_status() -> dict[str, Any]:
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {"active": False, "state": "unbekannt", "message": "Noch kein Status verfügbar"}


def _run(command: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(command, input=input_text, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"Befehl fehlgeschlagen: {command[0]}")
    return result.stdout.strip()


def generate_keys() -> tuple[str, str]:
    try:
        private_key = _run(["wg", "genkey"])
        public_key = _run(["wg", "pubkey"], private_key + "\n")
        return private_key, public_key
    except (OSError, subprocess.TimeoutExpired, ValueError):
        # X25519-Schlüssel müssen durch wg erzeugt werden. Keine unsichere Ersatzimplementierung.
        raise ValueError("WireGuard-Schlüssel konnten nicht erzeugt werden. Ist wireguard-tools installiert?")


def generate_preshared_key() -> str:
    try:
        return _run(["wg", "genpsk"])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise ValueError("Preshared Key konnte nicht erzeugt werden.")


def _valid_key(value: str, required: bool = False) -> str:
    value = value.strip()
    if not value and not required:
        return ""
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("Ungültiger WireGuard-Schlüssel") from exc
    if len(decoded) != 32:
        raise ValueError("Ungültiger WireGuard-Schlüssel")
    return value


def validate_config(supplied: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige WireGuard-Konfiguration")
    current = current or load_config()
    interface = str(supplied.get("interface", "wg0")).strip()
    if not INTERFACE_RE.fullmatch(interface):
        raise ValueError("Ungültiger Tunnelname")
    address = str(supplied.get("address", "")).strip()
    if address:
        for item in address.split(","):
            ipaddress.ip_interface(item.strip())
    mtu = int(supplied.get("mtu", 1420))
    if mtu < 576 or mtu > 9000:
        raise ValueError("MTU muss zwischen 576 und 9000 liegen")
    peer = supplied.get("peer", {})
    if not isinstance(peer, dict):
        raise ValueError("Ungültige Peer-Konfiguration")
    allowed_ips = str(peer.get("allowed_ips", "")).strip()
    if allowed_ips:
        for item in allowed_ips.split(","):
            ipaddress.ip_network(item.strip(), strict=False)
    keepalive = int(peer.get("persistent_keepalive", 25))
    if keepalive < 0 or keepalive > 65535:
        raise ValueError("Persistent Keepalive ist ungültig")
    private_key = str(supplied.get("private_key", "")).strip() or str(current.get("private_key", ""))
    public_key = str(supplied.get("public_key", "")).strip() or str(current.get("public_key", ""))
    if private_key:
        private_key = _valid_key(private_key)
    if public_key:
        public_key = _valid_key(public_key)
    peer_public = _valid_key(str(peer.get("public_key", "")), required=bool(supplied.get("enabled")))
    preshared = _valid_key(str(peer.get("preshared_key", "")))
    endpoint = str(peer.get("endpoint", "")).strip()
    if bool(supplied.get("enabled")) and (not address or not private_key or not endpoint or not allowed_ips):
        raise ValueError("Für einen aktiven Tunnel werden Adresse, privater Schlüssel, Endpoint und AllowedIPs benötigt")
    return {
        "enabled": bool(supplied.get("enabled")),
        "interface": interface,
        "autostart": bool(supplied.get("autostart", True)),
        "address": address,
        "dns": str(supplied.get("dns", "")).strip(),
        "mtu": mtu,
        "private_key": private_key,
        "public_key": public_key,
        "peer": {
            "name": str(peer.get("name", "VPN-Gegenstelle")).strip() or "VPN-Gegenstelle",
            "public_key": peer_public,
            "preshared_key": preshared,
            "endpoint": endpoint,
            "allowed_ips": allowed_ips,
            "persistent_keepalive": keepalive,
        },
    }


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(config))
    safe["private_key"] = ""
    safe["has_private_key"] = bool(config.get("private_key"))
    peer = safe.get("peer", {})
    peer["preshared_key"] = ""
    peer["has_preshared_key"] = bool(config.get("peer", {}).get("preshared_key"))
    return safe


def export_conf(config: dict[str, Any]) -> str:
    peer = config.get("peer", {})
    lines = ["[Interface]", f"PrivateKey = {config.get('private_key', '')}", f"Address = {config.get('address', '')}"]
    if config.get("dns"):
        lines.append(f"DNS = {config['dns']}")
    if config.get("mtu"):
        lines.append(f"MTU = {config['mtu']}")
    lines.extend(["", "[Peer]", f"PublicKey = {peer.get('public_key', '')}"])
    if peer.get("preshared_key"):
        lines.append(f"PresharedKey = {peer['preshared_key']}")
    lines.extend([
        f"Endpoint = {peer.get('endpoint', '')}",
        f"AllowedIPs = {peer.get('allowed_ips', '')}",
        f"PersistentKeepalive = {peer.get('persistent_keepalive', 25)}",
        "",
    ])
    return "\n".join(lines)


def import_conf(text: str) -> dict[str, Any]:
    parser = configparser.ConfigParser(strict=False)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ValueError(f"Konfigurationsdatei konnte nicht gelesen werden: {exc}") from exc
    if not parser.has_section("Interface") or not parser.has_section("Peer"):
        raise ValueError("Die Datei benötigt [Interface] und [Peer]")
    interface = parser["Interface"]
    peer = parser["Peer"]
    private_key = interface.get("PrivateKey", "").strip()
    public_key = ""
    if private_key:
        try:
            public_key = _run(["wg", "pubkey"], private_key + "\n")
        except Exception:
            public_key = ""
    supplied = {
        "enabled": False,
        "interface": "wg0",
        "autostart": True,
        "address": interface.get("Address", "").strip(),
        "dns": interface.get("DNS", "").strip(),
        "mtu": interface.getint("MTU", fallback=1420),
        "private_key": private_key,
        "public_key": public_key,
        "peer": {
            "name": "Importierte Gegenstelle",
            "public_key": peer.get("PublicKey", "").strip(),
            "preshared_key": peer.get("PresharedKey", "").strip(),
            "endpoint": peer.get("Endpoint", "").strip(),
            "allowed_ips": peer.get("AllowedIPs", "").strip(),
            "persistent_keepalive": peer.getint("PersistentKeepalive", fallback=25),
        },
    }
    return validate_config(supplied)
