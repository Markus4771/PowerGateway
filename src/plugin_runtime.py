#!/usr/bin/env python3
"""Zentrale Plugin-Laufzeit mit den eingebauten PowerGateway-Modulen."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from event_bus import bus
from plugin_framework import PluginManager
from runtime_config import merged_config


StatusProvider = Callable[[dict[str, Any]], dict[str, Any]]


class CoreModulePlugin:
    """Leichtgewichtiges Plugin für bestehende Kernfunktionen.

    Die Fachlogik bleibt zunächst in den bewährten Modulen. Dieses Plugin stellt
    einen einheitlichen Lebenszyklus, Status und Diagnose bereit und erlaubt die
    schrittweise Migration ohne Funktionsbruch.
    """

    version = "1.0"

    def __init__(self, plugin_id: str, name: str, provider: StatusProvider) -> None:
        self.plugin_id = plugin_id
        self.name = name
        self._provider = provider
        self._config: dict[str, Any] = {}
        self._events = bus
        self._running = False

    def initialize(self, config: dict[str, Any], events: Any) -> None:
        self._config = config
        self._events = events

    def start(self) -> None:
        self._running = True
        self._events.publish("module.started", {"module": self.plugin_id}, self.plugin_id)

    def stop(self) -> None:
        self._running = False
        self._events.publish("module.stopped", {"module": self.plugin_id}, self.plugin_id)

    def status(self) -> dict[str, Any]:
        result = self._provider(self._config)
        result.setdefault("ok", True)
        result["running"] = self._running
        return result

    def diagnose(self) -> dict[str, Any]:
        result = self.status()
        result["plugin_id"] = self.plugin_id
        result["name"] = self.name
        return result


def _application() -> dict[str, Any]:
    try:
        import webapp_legacy as legacy
        return merged_config(legacy.base_config())
    except Exception:
        return merged_config({})


def _status_file() -> dict[str, Any]:
    path = Path("/var/lib/powergateway/status.json")
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _usb_status(_: dict[str, Any]) -> dict[str, Any]:
    app = _application()
    meter = app.get("meter", {})
    source = str(meter.get("source", ""))
    status = _status_file()
    return {
        "ok": source != "usb_sml" or bool(status.get("meter_connected")),
        "enabled": source == "usb_sml",
        "source": source,
        "device": meter.get("device", "auto"),
        "connected": bool(status.get("meter_connected")),
    }


def _mqtt_status(_: dict[str, Any]) -> dict[str, Any]:
    app = _application()
    mqtt = app.get("mqtt", {})
    enabled = bool(mqtt.get("enabled"))
    status = _status_file()
    connected = bool(status.get("mqtt_connected"))
    return {
        "ok": not enabled or connected or bool(mqtt.get("host")),
        "enabled": enabled,
        "host": mqtt.get("host", ""),
        "connected": connected,
    }


def _ha_status(_: dict[str, Any]) -> dict[str, Any]:
    app = _application()
    mqtt = app.get("mqtt", {})
    enabled = bool(mqtt.get("homeassistant_discovery"))
    return {
        "ok": not enabled or bool(mqtt.get("host")),
        "enabled": enabled,
        "discovery_prefix": mqtt.get("discovery_prefix", "homeassistant"),
    }


def _wireguard_status(_: dict[str, Any]) -> dict[str, Any]:
    try:
        import wireguard_manager
        config = wireguard_manager.load_config()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    enabled = bool(config.get("enabled"))
    peer = config.get("peer", {})
    return {
        "ok": not enabled or bool(peer.get("endpoint")),
        "enabled": enabled,
        "endpoint": peer.get("endpoint", ""),
        "binary": bool(shutil.which("wg")),
    }


def _lte_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(shutil.which("mmcli")),
        "available": bool(shutil.which("mmcli")),
        "network_manager": bool(shutil.which("nmcli")),
    }


def _diagnostics_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "commands": {
            name: bool(shutil.which(name))
            for name in ("nmcli", "mmcli", "wg", "sqlite3", "journalctl")
        },
    }


manager = PluginManager(bus)
manager.register(CoreModulePlugin("usb_sml", "USB-SML", _usb_status))
manager.register(CoreModulePlugin("mqtt", "MQTT", _mqtt_status))
manager.register(CoreModulePlugin("homeassistant", "Home Assistant", _ha_status))
manager.register(CoreModulePlugin("wireguard", "WireGuard", _wireguard_status))
manager.register(CoreModulePlugin("lte", "LTE", _lte_status))
manager.register(CoreModulePlugin("diagnostics", "Diagnose", _diagnostics_status))
manager.start_all()


def module_status() -> dict[str, Any]:
    plugins = manager.status()
    return {
        "plugins": plugins,
        "events": bus.history(30),
        "ok": all(item.get("state") != "error" for item in plugins),
    }
