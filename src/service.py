#!/usr/bin/env python3
"""PowerGateway service bootstrap with modular SML/OBIS decoding."""
from __future__ import annotations

import json
import logging
from typing import Any

import powergateway as core
from sml_obis import KNOWN_OBIS, decode_obis_values


_original_telegram_payload = core.telegram_payload
_original_publish_or_buffer = core.publish_or_buffer
_original_publish_discovery = core.MqttPublisher.publish_discovery
_discovery_published: set[str] = set()


def telegram_payload(frame: bytes, gateway_name: str) -> dict[str, Any]:
    payload = _original_telegram_payload(frame, gateway_name)
    measurements = [item.to_dict() for item in decode_obis_values(frame)]
    payload["measurements"] = measurements
    payload["values"] = {item["key"]: item["value"] for item in measurements}
    if measurements:
        logging.info("OBIS-Werte erkannt: %s", ", ".join(item["key"] for item in measurements))
    else:
        logging.warning("SML-Telegramm enthält noch keine erkannten OBIS-Werte")
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
        "sw_version": "0.3.0-dev",
    }
    for obis, (key, name, unit, state_class) in KNOWN_OBIS.items():
        device_class = {
            "kWh": "energy",
            "Wh": "energy",
            "W": "power",
            "V": "voltage",
            "A": "current",
            "Hz": "frequency",
        }.get(unit)
        config: dict[str, Any] = {
            "name": name,
            "unique_id": f"{self.gateway_name}_{key}",
            "state_topic": f"{self.topic_prefix}/meter/values",
            "value_template": "{{ value_json." + key + " }}",
            "availability_topic": f"{self.topic_prefix}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
            "json_attributes_topic": f"{self.topic_prefix}/meter/values",
            "json_attributes_template": "{{ {'obis': '" + obis + "'} | tojson }}",
        }
        if unit:
            config["unit_of_measurement"] = unit
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        self.publish(
            f"{discovery_prefix}/sensor/{self.gateway_name}/{key}/config",
            json.dumps(config, separators=(",", ":"), ensure_ascii=False),
            retain=True,
        )
    _discovery_published.add(identity)
    logging.info("Home-Assistant-Discovery für OBIS-Sensoren veröffentlicht")


core.telegram_payload = telegram_payload
core.publish_or_buffer = publish_or_buffer
core.MqttPublisher.publish_discovery = publish_discovery


if __name__ == "__main__":
    raise SystemExit(core.main())
