#!/usr/bin/env python3
"""Network selection and diagnostics for PowerGateway.

Uses NetworkManager/nmcli as the system integration layer. The module does not
replace NetworkManager; it applies configured connection priorities and reports
which uplink is currently active.
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from typing import Any


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
    lan: NetworkLink | None = None
    wifi: NetworkLink | None = None
    lte: NetworkLink | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(command: list[str], timeout: float = 8.0) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _device_rows() -> list[tuple[str, str, str, str]]:
    output = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    rows: list[tuple[str, str, str, str]] = []
    for line in output.splitlines():
        parts = line.split(":", 3)
        if len(parts) == 4:
            rows.append(tuple(parts))
    return rows


def _address(interface: str) -> str | None:
    output = _run(["nmcli", "-g", "IP4.ADDRESS", "device", "show", interface])
    return output.splitlines()[0] if output else None


def snapshot(config: dict[str, Any]) -> NetworkSnapshot:
    network = config.get("network", {})
    order = [str(item).lower() for item in network.get("priority", ["lan", "wifi", "lte"])]
    priorities = {name: len(order) - index for index, name in enumerate(order)}
    rows = _device_rows()

    def make(kind: str, nm_type: str, default_interface: str) -> NetworkLink:
        section = network.get(kind, {})
        enabled = bool(section.get("enabled", True))
        configured_interface = str(section.get("interface", default_interface))
        candidates = [row for row in rows if row[1] == nm_type]
        selected = next((row for row in candidates if row[0] == configured_interface), None)
        if selected is None and str(section.get("interface", "auto")) == "auto":
            selected = next(iter(candidates), None)
        interface = selected[0] if selected else configured_interface
        state = selected[2] if selected else "not_found"
        connection = selected[3] if selected and selected[3] != "--" else None
        return NetworkLink(
            kind=kind,
            enabled=enabled,
            interface=interface,
            state=state,
            connection=connection,
            address=_address(interface) if enabled and state == "connected" else None,
            priority=priorities.get(kind, 0),
        )

    lan = make("lan", "ethernet", "eth0")
    wifi = make("wifi", "wifi", "wlan0")
    lte = make("lte", "gsm", "wwan0")
    links = {"lan": lan, "wifi": wifi, "lte": lte}
    active = next((name for name in order if links.get(name) and links[name].enabled and links[name].state == "connected"), "none")
    return NetworkSnapshot(active=active, online=active != "none", lan=lan, wifi=wifi, lte=lte)


def apply_priorities(config: dict[str, Any]) -> list[str]:
    """Apply NetworkManager autoconnect priorities to configured profiles."""
    network = config.get("network", {})
    order = [str(item).lower() for item in network.get("priority", ["lan", "wifi", "lte"])]
    base = 300
    messages: list[str] = []
    for index, kind in enumerate(order):
        section = network.get(kind, {})
        connection = str(section.get("connection", "")).strip()
        if not connection:
            continue
        priority = base - index * 100
        _run(["nmcli", "connection", "modify", connection, "connection.autoconnect", "yes"])
        _run(["nmcli", "connection", "modify", connection, "connection.autoconnect-priority", str(priority)])
        messages.append(f"{kind}: {connection} -> Priorität {priority}")
    return messages


def configure_wifi(ssid: str, password: str, connection_name: str = "PowerGateway-WLAN") -> bool:
    if not ssid:
        return False
    command = ["nmcli", "device", "wifi", "connect", ssid, "name", connection_name]
    if password:
        command.extend(["password", password])
    return bool(_run(command))


def configure_lte(apn: str, connection_name: str = "PowerGateway-LTE", username: str = "", password: str = "") -> bool:
    if not apn:
        return False
    existing = _run(["nmcli", "-g", "NAME", "connection", "show"]).splitlines()
    if connection_name not in existing:
        _run(["nmcli", "connection", "add", "type", "gsm", "ifname", "*", "con-name", connection_name, "apn", apn])
    command = ["nmcli", "connection", "modify", connection_name, "gsm.apn", apn]
    if username:
        command.extend(["gsm.username", username])
    if password:
        command.extend(["gsm.password", password])
    _run(command)
    return bool(_run(["nmcli", "connection", "up", connection_name]))
