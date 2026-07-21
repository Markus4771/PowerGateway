#!/usr/bin/env python3
"""Lokale, sichere WireGuard-Diagnosen ohne externe Cloud-Abhängigkeit."""
from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
import time
from typing import Any

from wireguard_manager import load_config, load_status
from wireguard_peers import load_peers


def _run(command: list[str], timeout: float = 8.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _check(label: str, ok: bool, message: str, recommendation: str = "") -> dict[str, Any]:
    return {"label": label, "ok": bool(ok), "message": message, "recommendation": recommendation}


def diagnose() -> dict[str, Any]:
    config = load_config()
    status = load_status()
    interface = str(config.get("interface", "wg0"))
    mode = str(config.get("mode", "client"))
    endpoint = str(config.get("public_endpoint", "") if mode == "server" else config.get("peer", {}).get("endpoint", ""))
    checks: list[dict[str, Any]] = []

    checks.append(_check("wireguard-tools", bool(shutil.which("wg") and shutil.which("wg-quick")), "wg und wg-quick sind installiert" if shutil.which("wg") and shutil.which("wg-quick") else "WireGuard-Werkzeuge fehlen", "Paket wireguard-tools installieren"))
    checks.append(_check("Schlüssel", bool(config.get("private_key") and config.get("public_key")), "Schlüsselpaar ist vorhanden" if config.get("private_key") and config.get("public_key") else "Schlüsselpaar ist unvollständig", "In der WebGUI ein Schlüsselpaar erzeugen und speichern"))
    checks.append(_check("Tunneladresse", bool(config.get("address")), str(config.get("address") or "Keine Tunneladresse"), "Eine eindeutige Tunnel-IP mit CIDR eintragen"))
    checks.append(_check("Tunnelstatus", bool(status.get("active")), str(status.get("message") or status.get("state") or "Unbekannt"), "Systemprotokoll und WireGuard-Konfiguration prüfen"))

    ok_route, route_output = _run(["ip", "route", "show"])
    address_ok = False
    if ok_route and config.get("address"):
        try:
            address_ok = any(str(ipaddress.ip_interface(item.strip()).network) in route_output for item in str(config.get("address")).split(",") if item.strip())
        except ValueError:
            address_ok = False
    checks.append(_check("Routing", address_ok, "Tunnelnetz ist in der Routingtabelle vorhanden" if address_ok else "Tunnelnetz wurde nicht in der Routingtabelle gefunden", "Tunnel aktivieren und wg-quick-Dienst prüfen"))

    forwarding = False
    try:
        forwarding = open("/proc/sys/net/ipv4/ip_forward", encoding="utf-8").read().strip() == "1"
    except OSError:
        pass
    if mode == "server":
        checks.append(_check("IPv4-Weiterleitung", forwarding, "IP-Forwarding ist aktiviert" if forwarding else "IP-Forwarding ist deaktiviert", "net.ipv4.ip_forward=1 aktivieren, wenn Clients andere Netze erreichen sollen"))

    host = endpoint.rsplit(":", 1)[0].strip("[]") if endpoint else ""
    if host:
        try:
            resolved = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
            checks.append(_check("Endpoint-DNS", True, f"{host} → {', '.join(resolved)}"))
        except socket.gaierror as exc:
            checks.append(_check("Endpoint-DNS", False, f"{host} konnte nicht aufgelöst werden: {exc}", "DNS-Namen oder Internetverbindung prüfen"))
    else:
        checks.append(_check("Endpoint", False, "Kein öffentlicher Endpoint konfiguriert", "Hostname/IP und UDP-Port eintragen"))

    ok_service, service_output = _run(["systemctl", "is-active", f"wg-quick@{interface}.service"])
    checks.append(_check("Systemdienst", ok_service, service_output or "unbekannt", f"journalctl -u wg-quick@{interface}.service prüfen"))

    peers = load_peers()
    enabled_peers = [peer for peer in peers if peer.get("enabled", True)]
    checks.append(_check("Peers", bool(enabled_peers) if mode == "server" else True, f"{len(enabled_peers)} aktive Peer(s)", "Mindestens einen Peer oder Client anlegen"))

    handshakes = [int(item.get("latest_handshake", 0) or 0) for item in status.get("peers", [])]
    recent = any(value and time.time() - value <= 180 for value in handshakes)
    if enabled_peers or mode == "client":
        checks.append(_check("Handshake", recent, "Mindestens ein aktueller Handshake" if recent else "Kein Handshake in den letzten 3 Minuten", "Endpoint, Portweiterleitung, Schlüssel und AllowedIPs prüfen"))

    return {
        "ok": all(item["ok"] for item in checks if item["label"] not in {"Handshake", "Tunnelstatus"}),
        "mode": mode,
        "interface": interface,
        "checks": checks,
        "status": status,
    }
