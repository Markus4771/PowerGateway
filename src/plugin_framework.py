#!/usr/bin/env python3
"""Kleine, konfigurationsbasierte Plugin-Grundlage für PowerGateway."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any, Protocol

from event_bus import EventBus, bus


class Plugin(Protocol):
    plugin_id: str
    name: str
    version: str

    def initialize(self, config: dict[str, Any], events: EventBus) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def status(self) -> dict[str, Any]: ...
    def diagnose(self) -> dict[str, Any]: ...


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    enabled: bool
    state: str = "loaded"
    error: str = ""


class PluginManager:
    def __init__(self, events: EventBus | None = None) -> None:
        self.events = events or bus
        self._plugins: dict[str, Plugin] = {}
        self._records: dict[str, PluginRecord] = {}

    def load_from_config(self, definitions: list[dict[str, Any]]) -> None:
        for definition in definitions:
            if not definition.get("enabled", True):
                continue
            module_name = str(definition.get("module", "")).strip()
            class_name = str(definition.get("class", "Plugin")).strip()
            if not module_name:
                continue
            try:
                plugin_class = getattr(import_module(module_name), class_name)
                plugin: Plugin = plugin_class()
                plugin.initialize(dict(definition.get("config") or {}), self.events)
                self._plugins[plugin.plugin_id] = plugin
                self._records[plugin.plugin_id] = PluginRecord(
                    plugin_id=plugin.plugin_id,
                    name=plugin.name,
                    version=plugin.version,
                    enabled=True,
                )
                self.events.publish("plugin.loaded", {"plugin_id": plugin.plugin_id}, "plugin-manager")
            except Exception as exc:  # Pluginfehler dürfen den Kern nicht stoppen.
                key = module_name or "unknown"
                self._records[key] = PluginRecord(key, key, "unknown", True, "error", str(exc))

    def start_all(self) -> None:
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.start()
                self._records[plugin_id].state = "running"
                self.events.publish("plugin.started", {"plugin_id": plugin_id}, "plugin-manager")
            except Exception as exc:
                self._records[plugin_id].state = "error"
                self._records[plugin_id].error = str(exc)

    def stop_all(self) -> None:
        for plugin_id, plugin in reversed(list(self._plugins.items())):
            try:
                plugin.stop()
                self._records[plugin_id].state = "stopped"
            except Exception as exc:
                self._records[plugin_id].state = "error"
                self._records[plugin_id].error = str(exc)

    def status(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for plugin_id, record in self._records.items():
            item = asdict(record)
            plugin = self._plugins.get(plugin_id)
            if plugin and record.state != "error":
                try:
                    item["details"] = plugin.status()
                except Exception as exc:
                    item["state"] = "error"
                    item["error"] = str(exc)
            result.append(item)
        return result

    def diagnostics(self) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for plugin_id, plugin in self._plugins.items():
            try:
                details[plugin_id] = plugin.diagnose()
            except Exception as exc:
                details[plugin_id] = {"ok": False, "error": str(exc)}
        return {"plugins": self.status(), "diagnostics": details}
