#!/usr/bin/env python3
"""Einrichtungs- und Hardwarediagnose für PowerGateway."""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import socket
from pathlib import Path
from typing import Any


def serial_devices() -> list[dict[str, str]]:
    paths = sorted(set(glob.glob("/dev/serial/by-id/*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")))
    return [{"path": path, "device": os.path.realpath(path), "name": Path(path).name} for path in paths]


def setup_check(application: dict[str, Any], network: dict[str, Any], status: dict[str, Any], wireguard: dict[str, Any]) -> dict[str, Any]:
    meter = application.get("meter", {})
    mqtt_config = application.get("mqtt", {})
    source = str(meter.get("source", ""))
    meter_configured = source == "simulation" or bool(meter.get("device")) or bool(meter.get("tasmota", {}).get("topic"))
    items = [
        {"id": "network", "label": "Netzwerk", "ok": bool(network.get("online") or network.get("active") not in {None, "", "none"})},
        {"id": "meter", "label": "Stromzähler", "ok": meter_configured, "detail": source or "nicht gewählt"},
        {"id": "meter_live", "label": "Messwerte", "ok": bool(status.get("meter_connected"))},
        {"id": "mqtt", "label": "MQTT", "ok": not bool(mqtt_config.get("enabled")) or bool(mqtt_config.get("host"))},
        {"id": "homeassistant", "label": "Home Assistant", "ok": not bool(mqtt_config.get("homeassistant_discovery")) or bool(mqtt_config.get("host"))},
        {"id": "wireguard", "label": "WireGuard", "ok": not bool(wireguard.get("enabled")) or bool(wireguard.get("peer", {}).get("endpoint"))},
    ]
    return {"complete": all(item["ok"] for item in items[:5]), "items": items}


def diagnostics() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    temperature = None
    try:
        temperature = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "load": [round(value, 2) for value in load],
        "temperature_c": temperature,
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "serial_devices": serial_devices(),
        "commands": {name: bool(shutil.which(name)) for name in ["nmcli", "mmcli", "wg", "wg-quick", "sqlite3"]},
    }
