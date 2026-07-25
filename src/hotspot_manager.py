#!/usr/bin/env python3
"""Robuste, eigenständige Hotspot-Steuerung für PowerGateway.

Der Hotspot bleibt technisch bei NetworkManager, wird aber vollständig und
reproduzierbar konfiguriert. Dadurch werden alte oder unvollständige Profile
entfernt und WPA2/CCMP ohne WPS-/PIN-Verfahren erzwungen.
"""
from __future__ import annotations

import ipaddress

from network_manager import CommandResult, active_connections, connection_names, run


def _channel(section: dict[str, object]) -> str:
    """Liefert einen für 2,4 GHz gültigen Kanal."""
    try:
        channel = int(section.get("channel", 6))
    except (TypeError, ValueError):
        channel = 6
    return str(channel if 1 <= channel <= 13 else 6)


def _addresses(section: dict[str, object], primary: str) -> str:
    """Erzeugt die NetworkManager-Adressliste inklusive LTE-Proxy-IP."""
    primary_interface = ipaddress.ip_interface(primary)
    proxy = str(section.get("proxy_address", "192.168.50.254/24")).strip()
    if not proxy:
        return primary
    proxy_interface = ipaddress.ip_interface(proxy)
    if proxy_interface.network != primary_interface.network:
        raise ValueError("Hotspot- und Proxy-Adresse müssen im selben Netz liegen")
    if proxy_interface.ip == primary_interface.ip:
        raise ValueError("Hotspot- und Proxy-Adresse müssen verschieden sein")
    return f"{primary},{proxy}"


def configure_hotspot(section: dict[str, object]) -> CommandResult:
    connection = str(section.get("connection", "PowerGateway-Setup"))
    interface = str(section.get("interface", "wlan0"))
    ssid = str(section.get("ssid", "PowerGateway-Setup")).strip() or "PowerGateway-Setup"
    password = str(section.get("password", "powergateway"))
    address = str(section.get("address", "192.168.50.1/24"))
    band = str(section.get("band", "bg"))

    try:
        addresses = _addresses(section, address)
    except ValueError as exc:
        return CommandResult(False, error=f"Ungültige Hotspot-Adresse: {exc}")
    if not 8 <= len(password) <= 63:
        return CommandResult(False, error="Das Hotspot-Passwort muss 8 bis 63 Zeichen haben")

    # WLAN-Funk einschalten und mögliche Soft-Blocks lösen. Die Befehle sind
    # absichtlich tolerant, damit auch Debian-Systeme ohne rfkill funktionieren.
    run(["rfkill", "unblock", "wifi"])
    run(["nmcli", "radio", "wifi", "on"])

    # Das Profil wird bei jedem Neuaufbau gelöscht. So bleiben keine alten
    # WPA-/WPS-/PMF-Einstellungen aus früheren PowerGateway-Versionen erhalten.
    if connection in active_connections():
        run(["nmcli", "connection", "down", connection])
    if connection in connection_names():
        result = run(["nmcli", "connection", "delete", connection])
        if not result.ok:
            return result

    result = run([
        "nmcli", "connection", "add",
        "type", "wifi",
        "ifname", interface,
        "con-name", connection,
        "autoconnect", "no",
        "ssid", ssid,
    ])
    if not result.ok:
        return result

    # WPA2-Personal mit AES/CCMP. proto=rsn verhindert den alten WPA1-Modus;
    # PMF optional verbessert die Kompatibilität mit Windows 11 und älteren
    # Raspberry-Pi-WLAN-Chipsätzen. NetworkManager bietet in diesem AP-Profil
    # kein WPS-PIN-Verfahren an.
    command = [
        "nmcli", "connection", "modify", connection,
        "connection.autoconnect", "no",
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", band,
        "802-11-wireless.channel", _channel(section),
        "802-11-wireless.hidden", "no",
        "802-11-wireless.ssid", ssid,
        "802-11-wireless-security.key-mgmt", "wpa-psk",
        "802-11-wireless-security.proto", "rsn",
        "802-11-wireless-security.pairwise", "ccmp",
        "802-11-wireless-security.group", "ccmp",
        "802-11-wireless-security.pmf", "2",
        "802-11-wireless-security.psk", password,
        "ipv4.method", "shared",
        "ipv4.addresses", addresses,
        "ipv6.method", "disabled",
    ]
    result = run(command)
    if not result.ok:
        return result

    return run(["nmcli", "connection", "up", connection], 30)


def stop_hotspot(connection: str = "PowerGateway-Setup") -> CommandResult:
    if connection not in active_connections():
        return CommandResult(True, output="Hotspot bereits inaktiv")
    return run(["nmcli", "connection", "down", connection])
