#!/usr/bin/env python3
"""Mehrere WireGuard-Peers und Client-Konfigurationen verwalten."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from wireguard_manager import DATA_DIR, _valid_key, generate_keys, generate_preshared_key, load_config

PEERS_PATH = DATA_DIR / "wireguard_peers.json"
NAME_RE = re.compile(r"^[^\x00-\x1f]{1,80}$")


def _atomic(value: list[dict[str, Any]]) -> None:
    PEERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".wireguard_peers.", dir=PEERS_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, PEERS_PATH)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_peers() -> list[dict[str, Any]]:
    try:
        value = json.loads(PEERS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def public_peers() -> list[dict[str, Any]]:
    result = []
    for peer in load_peers():
        safe = dict(peer)
        safe["preshared_key"] = ""
        safe["has_preshared_key"] = bool(peer.get("preshared_key"))
        result.append(safe)
    return result


def validate_peer(supplied: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige Peer-Konfiguration")
    current = current or {}
    name = str(supplied.get("name", current.get("name", "Peer"))).strip()
    if not NAME_RE.fullmatch(name):
        raise ValueError("Der Peer-Name ist ungültig")
    public_key = _valid_key(str(supplied.get("public_key", current.get("public_key", ""))), required=True)
    psk = str(supplied.get("preshared_key", "")).strip() or str(current.get("preshared_key", ""))
    psk = _valid_key(psk) if psk else ""
    allowed_ips = str(supplied.get("allowed_ips", current.get("allowed_ips", ""))).strip()
    if not allowed_ips:
        raise ValueError("AllowedIPs dürfen nicht leer sein")
    for item in allowed_ips.split(","):
        ipaddress.ip_network(item.strip(), strict=False)
    keepalive = int(supplied.get("persistent_keepalive", current.get("persistent_keepalive", 25)))
    if keepalive < 0 or keepalive > 65535:
        raise ValueError("Persistent Keepalive ist ungültig")
    return {
        "id": str(current.get("id") or supplied.get("id") or uuid.uuid4()),
        "name": name,
        "public_key": public_key,
        "preshared_key": psk,
        "endpoint": str(supplied.get("endpoint", current.get("endpoint", ""))).strip(),
        "allowed_ips": allowed_ips,
        "persistent_keepalive": keepalive,
        "enabled": bool(supplied.get("enabled", current.get("enabled", True))),
    }


def save_peer(supplied: dict[str, Any]) -> dict[str, Any]:
    peers = load_peers()
    peer_id = str(supplied.get("id", "")).strip()
    index = next((i for i, item in enumerate(peers) if item.get("id") == peer_id), None)
    current = peers[index] if index is not None else None
    peer = validate_peer(supplied, current)
    if index is None:
        peers.append(peer)
    else:
        peers[index] = peer
    _atomic(peers)
    return peer


def delete_peer(peer_id: str) -> bool:
    peers = load_peers()
    filtered = [peer for peer in peers if peer.get("id") != peer_id]
    if len(filtered) == len(peers):
        return False
    _atomic(filtered)
    return True


def peer_sections() -> str:
    lines: list[str] = []
    for peer in load_peers():
        if not peer.get("enabled", True):
            continue
        lines.extend(["", "[Peer]", f"# Name = {peer.get('name', 'Peer')}", f"PublicKey = {peer.get('public_key', '')}"])
        if peer.get("preshared_key"):
            lines.append(f"PresharedKey = {peer['preshared_key']}")
        if peer.get("endpoint"):
            lines.append(f"Endpoint = {peer['endpoint']}")
        lines.append(f"AllowedIPs = {peer.get('allowed_ips', '')}")
        keepalive = int(peer.get("persistent_keepalive", 0) or 0)
        if keepalive:
            lines.append(f"PersistentKeepalive = {keepalive}")
    return "\n".join(lines) + ("\n" if lines else "")


def create_client(name: str, client_address: str, endpoint: str, allowed_ips: str = "0.0.0.0/0", dns: str = "") -> dict[str, Any]:
    config = load_config()
    server_public = str(config.get("public_key", "")).strip()
    if not server_public:
        raise ValueError("Zuerst muss für PowerGateway ein WireGuard-Schlüsselpaar erzeugt und gespeichert werden")
    ipaddress.ip_interface(client_address)
    for item in allowed_ips.split(","):
        ipaddress.ip_network(item.strip(), strict=False)
    if not endpoint.strip():
        raise ValueError("Der öffentliche Endpoint des PowerGateway fehlt")
    private_key, public_key = generate_keys()
    psk = generate_preshared_key()
    peer = save_peer({
        "name": name,
        "public_key": public_key,
        "preshared_key": psk,
        "allowed_ips": str(ipaddress.ip_interface(client_address).ip) + "/32",
        "persistent_keepalive": 25,
        "enabled": True,
    })
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {client_address}",
    ]
    if dns.strip():
        lines.append(f"DNS = {dns.strip()}")
    lines.extend([
        "",
        "[Peer]",
        f"PublicKey = {server_public}",
        f"PresharedKey = {psk}",
        f"Endpoint = {endpoint.strip()}",
        f"AllowedIPs = {allowed_ips.strip()}",
        "PersistentKeepalive = 25",
        "",
    ])
    return {"peer": {**peer, "preshared_key": "", "has_preshared_key": True}, "config": "\n".join(lines)}


def qr_svg(text: str) -> str:
    if len(text) > 8192:
        raise ValueError("Konfiguration ist für einen QR-Code zu groß")
    try:
        result = subprocess.run(
            ["qrencode", "-t", "SVG", "-o", "-"],
            input=text,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("QR-Code konnte nicht erzeugt werden. Ist qrencode installiert?") from exc
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "QR-Code konnte nicht erzeugt werden")
    return result.stdout
