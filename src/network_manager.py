#!/usr/bin/env python3
"""NetworkManager integration for PowerGateway.

The module manages one LAN uplink, one WLAN client, one LTE uplink and an
optional WLAN setup hotspot. All operating-system changes are delegated to
NetworkManager via ``nmcli``.
"""
from __future__ import annotations

import ipaddress
import subprocess
from dataclasses import asdict, dataclass
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
        return CommandResult(
            ok=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
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
    lte = make("lte", "gsm", "wwan0")
    links = {"lan": lan, "wifi": wifi, "lte": lte}
    active = next((name for name in order if links[name].enabled and links[name].state == "connected"), "none")
    return NetworkSnapshot(active, active != "none", hotspot_active, lan, wifi, lte)


def configure_lan(section: dict[str, Any]) -> CommandResult:
    connection = str(section.get("connection", "PowerGateway-LAN"))
    interface = str(section.get("interface", "eth0"))
    existing = connection_names()
    if connection not in existing:
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
    apn = str(section.get("apn", "")).strip()
    if not apn:
        return CommandResult(False, error="Kein LTE-APN angegeben")
    connection = str(section.get("connection", "PowerGateway-LTE"))
    if connection not in connection_names():
        result = run(["nmcli", "connection", "add", "type", "gsm", "ifname", "*", "con-name", connection, "apn", apn])
        if not result.ok:
            return result
    command = ["nmcli", "connection", "modify", connection, "gsm.apn", apn, "connection.autoconnect", "yes"]
    username = str(section.get("username", ""))
    password = str(section.get("password", ""))
    pin = str(section.get("pin", ""))
    if username:
        command.extend(["gsm.username", username])
    if password:
        command.extend(["gsm.password", password])
    if pin:
        command.extend(["gsm.pin", pin])
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
    command = [
        "nmcli", "connection", "modify", connection,
        "802-11-wireless.mode", "ap", "802-11-wireless.band", str(section.get("band", "bg")),
        "802-11-wireless.ssid", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
        "ipv4.method", "shared", "ipv4.addresses", address, "ipv6.method", "disabled",
    ]
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
    for index, kind in enumerate(order):
        connection = str(network.get(kind, {}).get("connection", "")).strip()
        if not connection:
            continue
        priority = 300 - index * 100
        run(["nmcli", "connection", "modify", connection, "connection.autoconnect", "yes", "connection.autoconnect-priority", str(priority)])
        messages.append(f"{kind}: {connection} -> Priorität {priority}")
    return messages
