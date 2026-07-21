#!/usr/bin/env python3
"""Modularer Einrichtungsassistent für PowerGateway."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


Check = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass(frozen=True)
class WizardStep:
    step_id: str
    title: str
    description: str
    section: str
    required: bool = True


STEPS = [
    WizardStep("welcome", "Willkommen", "PowerGateway und Zielsystem prüfen.", "setup"),
    WizardStep("network", "Netzwerk", "LAN, WLAN oder LTE-Verbindung prüfen.", "network"),
    WizardStep("meter", "Stromzähler", "USB-SML oder MQTT als Datenquelle auswählen.", "meter"),
    WizardStep("meter_test", "Messwerttest", "Echte Messwerte vom Zähler empfangen.", "meter"),
    WizardStep("mqtt", "MQTT", "Broker und Zugangsdaten prüfen.", "mqtt"),
    WizardStep("homeassistant", "Home Assistant", "Discovery-Sensoren prüfen und veröffentlichen.", "homeassistant", False),
    WizardStep("wireguard", "WireGuard", "Optionalen Fernzugriff prüfen.", "wireguard", False),
    WizardStep("summary", "Abschluss", "Einrichtung zusammenfassen und abschließen.", "setup"),
]


def _configured_meter(application: dict[str, Any]) -> tuple[bool, str]:
    meter = application.get("meter", {})
    source = str(meter.get("source", "")).strip()
    configured = source == "simulation" or bool(meter.get("device")) or bool(meter.get("tasmota", {}).get("topic"))
    return configured, source or "keine Datenquelle gewählt"


def build_wizard_state(
    application: dict[str, Any],
    network: dict[str, Any],
    status: dict[str, Any],
    wireguard: dict[str, Any],
    version_file: str | Path | None = None,
) -> dict[str, Any]:
    mqtt = application.get("mqtt", {})
    meter_ok, meter_detail = _configured_meter(application)
    network_ok = bool(network.get("online") or network.get("active") not in {None, "", "none"})
    mqtt_ok = not bool(mqtt.get("enabled")) or bool(mqtt.get("host"))
    ha_enabled = bool(mqtt.get("homeassistant_discovery"))
    wg_enabled = bool(wireguard.get("enabled"))
    checks: dict[str, tuple[bool, str]] = {
        "welcome": (True, "System bereit"),
        "network": (network_ok, str(network.get("active") or "offline")),
        "meter": (meter_ok, meter_detail),
        "meter_test": (bool(status.get("meter_connected")), "Messwerte empfangen" if status.get("meter_connected") else "noch keine Messwerte"),
        "mqtt": (mqtt_ok, str(mqtt.get("host") or "deaktiviert")),
        "homeassistant": (not ha_enabled or mqtt_ok, "aktiviert" if ha_enabled else "optional/deaktiviert"),
        "wireguard": (not wg_enabled or bool(wireguard.get("peer", {}).get("endpoint")), "aktiviert" if wg_enabled else "optional/deaktiviert"),
        "summary": (False, "Einrichtung noch nicht abgeschlossen"),
    }
    items = []
    first_open = None
    for index, step in enumerate(STEPS, start=1):
        ok, detail = checks[step.step_id]
        if first_open is None and step.required and not ok:
            first_open = step.step_id
        items.append({**asdict(step), "order": index, "ok": ok, "detail": detail})
    required_complete = all(item["ok"] for item in items if item["required"] and item["step_id"] != "summary")
    for item in items:
        if item["step_id"] == "summary":
            item["ok"] = required_complete
            item["detail"] = "bereit zum Abschließen" if required_complete else "Pflichtschritte offen"
    version = "unknown"
    if version_file:
        try:
            version = Path(version_file).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return {
        "version": version,
        "complete": required_complete,
        "current_step": first_open or "summary",
        "progress": round(sum(1 for item in items if item["ok"]) * 100 / len(items)),
        "steps": items,
    }
