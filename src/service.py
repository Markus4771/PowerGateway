#!/usr/bin/env python3
"""PowerGateway service bootstrap with modular SML/OBIS decoding."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import powergateway as core
from simulator import SimulatedSerial, SmlSimulator
from sml_obis import OBIS_REGISTRY, decode_obis_values

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

LATEST_VALUES_PATH = Path(os.environ.get("POWERGATEWAY_LATEST_VALUES", "/var/lib/powergateway/latest_values.json"))
_original_telegram_payload = core.telegram_payload
_original_publish_or_buffer = core.publish_or_buffer
_original_publish_discovery = core.MqttPublisher.publish_discovery
_original_resolve_meter_device = core.resolve_meter_device
_original_serial = core.serial.Serial
_discovery_published: set[str] = set()
_simulator: SmlSimulator | None = None


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _simulation_config() -> dict[str, Any]:
    try:
        with core.CONFIG_PATH.open("rb") as handle:
            return tomllib.load(handle).get("meter", {})
    except (OSError, ValueError):
        return {}


def enable_simulation_if_configured() -> bool:
    global _simulator
    meter = _simulation_config()
    if str(meter.get("mode", "serial")).lower() != "simulation":
        return False

    profile = str(meter.get("simulation_profile", "generic"))
    interval = float(meter.get("simulation_interval", 5.0))
    seed_value = meter.get("simulation_seed")
    seed = int(seed_value) if seed_value is not None else None
    _simulator = SmlSimulator(profile=profile, interval=interval, seed=seed)

    def simulated_device(configured: str) -> str:
        del configured
        return f"simulation://{profile}"

    def simulated_serial(*args: Any, **kwargs: Any) -> SimulatedSerial:
        del args, kwargs
        assert _simulator is not None
        return SimulatedSerial(_simulator)

    core.resolve_meter_device = simulated_device
    core.serial.Serial = simulated_serial  # type: ignore[assignment]
    logging.warning("SIMULATIONSMODUS aktiv: Profil=%s, Intervall=%.1fs", profile, interval)
    return True


def telegram_payload(frame: bytes, gateway_name: str) -> dict[str, Any]:
    payload = _original_telegram_payload(frame, gateway_name)
    measurements = [item.to_dict() for item in decode_obis_values(frame)]
    payload["measurements"] = measurements
    payload["values"] = {item["key"]: item["value"] for item in measurements}
    payload["unknown_obis"] = [item["obis"] for item in measurements if not item.get("known", True)]
    payload["simulation"] = _simulator is not None
    payload["simulation_profile"] = _simulator.profile_key if _simulator else None
    if measurements:
        latest = {
            **payload["values"],
            "gateway": gateway_name,
            "received_at": payload.get("received_at"),
            "telegram_sha256": payload.get("sha256"),
            "measurements": measurements,
            "unknown_obis": payload["unknown_obis"],
            "simulation": payload["simulation"],
            "simulation_profile": payload["simulation_profile"],
        }
        _atomic_write(LATEST_VALUES_PATH, latest)
        logging.info("OBIS-Werte erkannt: %s", ", ".join(item["key"] for item in measurements))
        if payload["unknown_obis"]:
            logging.info("Unbekannte OBIS-Kennzahlen: %s", ", ".join(payload["unknown_obis"]))
    else:
        logging.warning("SML-Telegramm enthält keine auswertbaren numerischen OBIS-Werte")
    return payload


def publish_or_buffer(
    publisher: core.MqttPublisher,
    buffer: core.MessageBuffer,
    topic: str,
    payload: str,
) -> None:
    _original_publish_or_buffer(publisher, buffer, topic, payload)
    if not topic.endswith("/meter/raw"):
        return
    try:
        decoded = json.loads(payload)
        values = decoded.get("values", {})
        measurements = decoded.get("measurements", [])
        if not values:
            return
        state = {
            **values,
            "received_at": decoded.get("received_at"),
            "telegram_sha256": decoded.get("sha256"),
            "measurements": measurements,
            "unknown_obis": decoded.get("unknown_obis", []),
            "simulation": decoded.get("simulation", False),
            "simulation_profile": decoded.get("simulation_profile"),
        }
        _original_publish_or_buffer(
            publisher,
            buffer,
            f"{publisher.topic_prefix}/meter/values",
            json.dumps(state, separators=(",", ":"), ensure_ascii=False),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logging.warning("Messwerte konnten nicht veröffentlicht werden: %s", exc)


def publish_discovery(self: core.MqttPublisher) -> None:
    _original_publish_discovery(self)
    if not self.connected or not bool(self.config.get("homeassistant_discovery", True)):
        return
    identity = f"{self.gateway_name}:{self.topic_prefix}"
    if identity in _discovery_published:
        return

    discovery_prefix = str(self.config.get("discovery_prefix", "homeassistant"))
    device = {
        "identifiers": [self.gateway_name],
        "name": self.gateway_name,
        "manufacturer": "PowerGateway",
        "model": "Raspberry Pi Meter Gateway",
        "sw_version": "0.7.0-dev",
    }
    published_keys: set[str] = set()
    for obis, definition in OBIS_REGISTRY.items():
        if definition.key in published_keys or definition.diagnostic:
            continue
        config: dict[str, Any] = {
            "name": definition.name,
            "unique_id": f"{self.gateway_name}_{definition.key}",
            "state_topic": f"{self.topic_prefix}/meter/values",
            "value_template": "{{ value_json." + definition.key + " }}",
            "availability_topic": f"{self.topic_prefix}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
            "json_attributes_topic": f"{self.topic_prefix}/meter/values",
            "json_attributes_template": "{{ {'obis': '" + obis + "'} | tojson }}",
        }
        if definition.unit:
            config["unit_of_measurement"] = definition.unit
        if definition.device_class:
            config["device_class"] = definition.device_class
        if definition.state_class:
            config["state_class"] = definition.state_class
        self.publish(
            f"{discovery_prefix}/sensor/{self.gateway_name}/{definition.key}/config",
            json.dumps(config, separators=(",", ":"), ensure_ascii=False),
            retain=True,
        )
        published_keys.add(definition.key)
    _discovery_published.add(identity)
    logging.info("Home-Assistant-Discovery für %d OBIS-Sensoren veröffentlicht", len(published_keys))


core.telegram_payload = telegram_payload
core.publish_or_buffer = publish_or_buffer
core.MqttPublisher.publish_discovery = publish_discovery


if __name__ == "__main__":
    enable_simulation_if_configured()
    raise SystemExit(core.main())
