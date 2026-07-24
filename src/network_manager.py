#!/usr/bin/env python3
"""NetworkManager integration for PowerGateway.

Unterstützt LAN, WLAN, klassische GSM/MBIM/QMI-Modems und LTE-Sticks im
USB-Ethernet-/HiLink-/CDC-Ethernet-Modus, beispielsweise den ZTE MF833U1.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    ok: bool
    output: str = ""
    error: str = ""


@dataclass
class NetworkLink:
    kind: str
    enabled: bool
    interface: str
    state: str = "unknown"
    connection: str | None = None
    address: str | None = None
    priority: int = 0
    mode: str | None = None
    vendor: str | None = None
    model: str | None = None
    usb_id: str | None = None
    driver: str | None = None
    gateway: str | None = None
    internet: bool | None = None


@dataclass
class NetworkSnapshot:
    active: str = "none"
    online: bool = False
    hotspot_active: bool = False
    lan: NetworkLink | None = None
    wifi: NetworkLink | None = None
    lte: NetworkLink | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run(command: list[str], timeout: float = 15.0) -> CommandResult:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return CommandResult(result.returncode == 0, result.stdout.strip(), result.stderr.strip())
    except FileNotFoundError:
        return CommandResult(False, error=f"Befehl nicht installiert: {command[0]}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, error=str(exc))


def _output(command: list[str], timeout: float = 15.0) -> str:
    result = run(command, timeout)
    return result.output if result.ok else ""


def _device_rows() -> list[tuple[str, str, str, str]]:
    output = _output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    rows: list[tuple[str, str, str, str]] = []
    for line in output.splitlines():
        parts = line.split(":", 3)
        if len(parts) == 4:
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def _address(interface: str) -> str | None:
    output = _output(["nmcli", "-g", "IP4.ADDRESS", "device", "show", interface])
    return output.splitlines()[0] if output else None


def _gateway(interface: str) -> str | None:
    output = _output(["nmcli", "-g", "IP4.GATEWAY", "device", "show", interface])
    return output.splitlines()[0] if output else None


def _internet_via(interface: str) -> bool:
    if not interface:
        return False
    result = run(["ping", "-I", interface, "-c", "1", "-W", "3", "1.1.1.1"], 5)
    return result.ok


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _usb_parent(interface: str) -> Path | None:
    path = Path("/sys/class/net") / interface / "device"
    try:
        current = path.resolve()
    except OSError:
        return None
    for candidate in [current, *current.parents]:
        if (candidate / "idVendor").exists() and (candidate / "idProduct").exists():
            return candidate
    return None


def _usb_metadata(interface: str) -> dict[str, str]:
    parent = _usb_parent(interface)
    if parent is None:
        return {}
    vendor_id = _read_text(parent / "idVendor").lower()
    product_id = _read_text(parent / "idProduct").lower()
    manufacturer = _read_text(parent / "manufacturer")
    product = _read_text(parent / "product")
    driver = ""
    try:
        driver = (Path("/sys/class/net") / interface / "device" / "driver").resolve().name
    except OSError:
        pass
    known = {
        "19d2:1706": ("ZTE", "MF833U1"),
    }
    known_vendor, known_model = known.get(f"{vendor_id}:{product_id}", ("", ""))
    return {
        "usb_id": f"{vendor_id}:{product_id}" if vendor_id and product_id else "",
        "vendor": known_vendor or manufacturer or vendor_id,
        "model": known_model or product or product_id,
        "driver": driver,
    }


def _lte_mode(nm_type: str, driver: str) -> str:
    if nm_type == "gsm":
        return "ModemManager/GSM"
    modes = {
        "cdc_ether": "CDC Ethernet",
        "rndis_host": "RNDIS/USB-Ethernet",
        "cdc_ncm": "NCM",
        "cdc_mbim": "MBIM",
        "qmi_wwan": "QMI",
    }
    return modes.get(driver, "USB-Ethernet")


def _lte_candidate(rows: list[tuple[str, str, str, str]], configured: str) -> tuple[str, str, str, str] | None:
    gsm = [row for row in rows if row[1] in {"gsm", "wwan"}]
    usb_ethernet: list[tuple[str, str, str, str]] = []
    for row in rows:
        if row[1] != "ethernet":
            continue
        metadata = _usb_metadata(row[0])
        if metadata.get("driver") in {"cdc_ether", "rndis_host", "cdc_ncm", "cdc_mbim", "qmi_wwan"}:
            usb_ethernet.append(row)
        elif metadata.get("usb_id", "").startswith(("19d2:", "12d1:", "2c7c:", "1199:", "1e0e:")):
            usb_ethernet.append(row)
    candidates = gsm + usb_ethernet
    if configured and configured != "auto":
        return next((row for row in candidates if row[0] == configured), None)
    return next(iter(candidates), None)


def connection_names() -> set[str]:
    return {line for line in _output(["nmcli", "-g", "NAME", "connection", "show"]).splitlines() if line}


def active_connections() -> set[str]:
    return {line for line in _output(["nmcli", "-g", "NAME", "connection", "show", "--active"]).splitlines() if line}


def wifi_scan(interface: str = "") -> list[dict[str, Any]]:
    command = ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list", "--rescan", "yes"]
    if interface and interface != "auto":
        command.extend(["ifname", interface])
    output = _output(command, 20)
    networks: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        parts = line.rsplit(":", 3)
        if len(parts) != 4 or not parts[0]:
            continue
        ssid, signal, security, in_use = parts
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        candidate = {"ssid": ssid, "signal": strength, "security": security or "offen", "active": in_use == "*"}
        if ssid not in networks or strength > int(networks[ssid]["signal"]):
            networks[ssid] = candidate
    return sorted(networks.values(), key=lambda item: (not item["active"], -int(item["signal"]), item["ssid"].lower()))


def snapshot(config: dict[str, Any]) -> NetworkSnapshot:
    network = config.get("network", {})
    order = [str(item).lower() for item in network.get("priority", ["lan", "wifi", "lte"])]
    priorities = {name: len(order) - index for index, name in enumerate(order)}
    rows = _device_rows()
    hotspot_name = str(network.get("hotspot", {}).get("connection", "PowerGateway-Setup"))
    hotspot_active = hotspot_name in active_connections()

    def make(kind: str, nm_type: str, default_interface: str) -> NetworkLink:
        section = network.get(kind, {})
        enabled = bool(section.get("enabled", True))
        configured_interface = str(section.get("interface", "auto"))
        candidates = [row for row in rows if row[1] == nm_type]
        selected = next((row for row in candidates if row[0] == configured_interface), None)
        if selected is None and configured_interface == "auto":
            selected = next(iter(candidates), None)
        interface = selected[0] if selected else default_interface
        state = selected[2] if selected else "not_found"
        connection = selected[3] if selected and selected[3] != "--" else None
        if kind == "wifi" and connection == hotspot_name:
            state = "hotspot"
        return NetworkLink(kind, enabled, interface, state, connection, _address(interface) if state in {"connected", "hotspot"} else None, priorities.get(kind, 0))

    lan = make("lan", "ethernet", "eth0")
    wifi = make("wifi", "wifi", "wlan0")

    lte_section = network.get("lte", {})
    lte_enabled = bool(lte_section.get("enabled", True))
    configured_lte = str(lte_section.get("interface", "auto"))
    selected_lte = _lte_candidate(rows, configured_lte)
    if selected_lte:
        interface, nm_type, state, connection_name = selected_lte
        metadata = _usb_metadata(interface)
        address = _address(interface) if state == "connected" else None
        lte = NetworkLink(
            "lte", lte_enabled, interface, state,
            connection_name if connection_name != "--" else None,
            address, priorities.get("lte", 0),
            _lte_mode(nm_type, metadata.get("driver", "")),
            metadata.get("vendor") or None,
            metadata.get("model") or None,
            metadata.get("usb_id") or None,
            metadata.get("driver") or None,
            _gateway(interface) if state == "connected" else None,
            _internet_via(interface) if state == "connected" else False,
        )
    else:
        lte = NetworkLink("lte", lte_enabled, configured_lte if configured_lte != "auto" else "wwan0", "not_found", priority=priorities.get("lte", 0))

    links = {"lan": lan, "wifi": wifi, "lte": lte}
    active = next((name for name in order if links[name].enabled and links[name].state == "connected"), "none")
    return NetworkSnapshot(active, active != "none", hotspot_active, lan, wifi, lte)


def configure_lan(section: dict[str, Any]) -> CommandResult:
    connection = str(section.get("connection", "PowerGateway-LAN"))
    interface = str(section.get("interface", "eth0"))
    if connection not in connection_names():
        result = run(["nmcli", "connection", "add", "type", "ethernet", "ifname", interface if interface != "auto" else "*", "con-name", connection])
        if not result.ok:
            return result
    commands = [["nmcli", "connection", "modify", connection, "connection.autoconnect", "yes"]]
    if bool(section.get("dhcp", True)):
        commands.append(["nmcli", "connection", "modify", connection, "ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", ""])
    else:
        address = str(section.get("address", "")).strip()
        gateway = str(section.get("gateway", "")).strip()
        try:
            ipaddress.ip_interface(address)
            if gateway:
                ipaddress.ip_address(gateway)
        except ValueError as exc:
            return CommandResult(False, error=f"Ungültige LAN-Adresse: {exc}")
        dns = ",".join(str(item) for item in section.get("dns", []) if str(item).strip())
        commands.append(["nmcli", "connection", "modify", connection, "ipv4.method", "manual", "ipv4.addresses", address, "ipv4.gateway", gateway, "ipv4.dns", dns])
    for command in commands:
        result = run(command)
        if not result.ok:
            return result
    return run(["nmcli", "connection", "up", connection])


def configure_wifi(section: dict[str, Any]) -> CommandResult:
    ssid = str(section.get("ssid", "")).strip()
    if not ssid:
        return CommandResult(False, error="Keine WLAN-SSID angegeben")
    password = str(section.get("password", ""))
    connection = str(section.get("connection", "PowerGateway-WLAN"))
    interface = str(section.get("interface", "auto"))
    if connection in connection_names():
        run(["nmcli", "connection", "delete", connection])
    command = ["nmcli", "device", "wifi", "connect", ssid, "name", connection]
    if interface != "auto":
        command.extend(["ifname", interface])
    if password:
        command.extend(["password", password])
    result = run(command, 30)
    if result.ok:
        run(["nmcli", "connection", "modify", connection, "connection.autoconnect", "yes"])
    return result


def configure_lte(section: dict[str, Any]) -> CommandResult:
    interface = str(section.get("interface", "auto"))
    rows = _device_rows()
    selected = _lte_candidate(rows, interface)
    if selected and selected[1] == "ethernet":
        device, _, state, connection_name = selected
        if state == "connected":
            return CommandResult(True, output=f"LTE über USB-Ethernet bereits verbunden: {device}")
        if connection_name and connection_name != "--":
            return run(["nmcli", "connection", "up", connection_name], 30)
        return run(["nmcli", "device", "connect", device], 30)

    apn = str(section.get("apn", "")).strip()
    if not apn:
        return CommandResult(False, error="Kein LTE-APN angegeben; USB-Ethernet-Sticks benötigen normalerweise keinen APN in PowerGateway")
    connection = str(section.get("connection", "PowerGateway-LTE"))
    if connection not in connection_names():
        result = run(["nmcli", "connection", "add", "type", "gsm", "ifname", "*", "con-name", connection, "apn", apn])
        if not result.ok:
            return result
    command = ["nmcli", "connection", "modify", connection, "gsm.apn", apn, "connection.autoconnect", "yes"]
    for key, property_name in (("username", "gsm.username"), ("password", "gsm.password"), ("pin", "gsm.pin")):
        value = str(section.get(key, ""))
        if value:
            command.extend([property_name, value])
    result = run(command)
    return run(["nmcli", "connection", "up", connection], 30) if result.ok else result


def configure_hotspot(section: dict[str, Any]) -> CommandResult:
    connection = str(section.get("connection", "PowerGateway-Setup"))
    interface = str(section.get("interface", "wlan0"))
    ssid = str(section.get("ssid", "PowerGateway-Setup")).strip() or "PowerGateway-Setup"
    password = str(section.get("password", "powergateway"))
    address = str(section.get("address", "192.168.50.1/24"))
    try:
        ipaddress.ip_interface(address)
    except ValueError as exc:
        return CommandResult(False, error=f"Ungültige Hotspot-Adresse: {exc}")
    if len(password) < 8:
        return CommandResult(False, error="Das Hotspot-Passwort muss mindestens 8 Zeichen haben")
    if connection not in connection_names():
        result = run(["nmcli", "connection", "add", "type", "wifi", "ifname", interface, "con-name", connection, "autoconnect", "no", "ssid", ssid])
        if not result.ok:
            return result
    command = ["nmcli", "connection", "modify", connection, "802-11-wireless.mode", "ap", "802-11-wireless.band", str(section.get("band", "bg")), "802-11-wireless.ssid", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password, "ipv4.method", "shared", "ipv4.addresses", address, "ipv6.method", "disabled"]
    result = run(command)
    return run(["nmcli", "connection", "up", connection], 30) if result.ok else result


def stop_hotspot(connection: str = "PowerGateway-Setup") -> CommandResult:
    if connection not in active_connections():
        return CommandResult(True, output="Hotspot bereits inaktiv")
    return run(["nmcli", "connection", "down", connection])


def apply_priorities(config: dict[str, Any]) -> list[str]:
    network = config.get("network", {})
    order = [str(item).lower() for item in network.get("priority", ["lan", "wifi", "lte"])]
    messages: list[str] = []
    current = snapshot(config)
    links = {"lan": current.lan, "wifi": current.wifi, "lte": current.lte}
    for index, kind in enumerate(order):
        configured = str(network.get(kind, {}).get("connection", "")).strip()
        detected = links.get(kind).connection if links.get(kind) else None
        connection = configured or detected or ""
        if not connection:
            continue
        priority = 300 - index * 100
        run(["nmcli", "connection", "modify", connection, "connection.autoconnect", "yes", "connection.autoconnect-priority", str(priority)])
        messages.append(f"{kind}: {connection} -> Priorität {priority}")
    return messages
