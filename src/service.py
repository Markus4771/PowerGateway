#!/usr/bin/env python3
"""PowerGateway service bootstrap with modular meter sources and OBIS decoding."""
from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import powergateway as core
from meter_sources import MeterReading, TasmotaMqttSource
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
_discovery_published: set[str] = set()
_simulator: SmlSimulator | None = None


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _load_config() -> dict[str, Any]:
    with core.CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _meter_config() -> dict[str, Any]:
    try:
        return _load_config().get("meter", {})
    except (OSError, ValueError):
        return {}


def enable_simulation_if_configured() -> bool:
    global _simulator
    meter = _meter_config()
    if str(meter.get("source", meter.get("mode", "serial"))).lower() != "simulation":
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
    payload["source"] = "simulation" if _simulator is not None else "usb_sml"
    payload["simulation"] = _simulator is not None
    payload["simulation_profile"] = _simulator.profile_key if _simulator else None
    if measurements:
        latest = {
            **payload["values"],
            "gateway": gateway_name,
            "source": payload["source"],
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
            "source": decoded.get("source", "usb_sml"),
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
        "model": "Modulares Meter Gateway",
        "sw_version": "0.8.0-dev",
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
    logging.info("Home-Assistant-Discovery für %d Messwertsensoren veröffentlicht", len(published_keys))


def _normalise_tasmota_reading(reading: MeterReading, gateway_name: str) -> dict[str, Any]:
    return {
        **reading.values,
        "gateway": gateway_name,
        "source": reading.source,
        "received_at": reading.received_at,
        "simulation": False,
        "raw": reading.raw,
    }


def run_tasmota_source(config: dict[str, Any]) -> int:
    gateway_config = config.get("gateway", {})
    meter_config = config.get("meter", {})
    source_config = dict(config.get("mqtt", {}))
    source_config.update(meter_config.get("tasmota", {}))
    logging.basicConfig(
        level=getattr(logging, str(gateway_config.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGTERM, core.stop_service)
    signal.signal(signal.SIGINT, core.stop_service)

    gateway_name = str(gateway_config.get("name", "powergateway"))
    status_path = Path(str(gateway_config.get("status_path", "/var/lib/powergateway/status.json")))
    buffer_config = config.get("buffer", {})
    message_buffer = core.MessageBuffer(str(buffer_config.get("path", "/var/lib/powergateway/buffer.db")))
    publisher = core.MqttPublisher(config.get("mqtt", {}), gateway_name)
    source = TasmotaMqttSource(source_config)
    status = core.GatewayStatus(version="0.8.0-dev", started_at=core.utc_now(), updated_at=core.utc_now())
    status.meter_device = source.device_name
    next_health_check = 0.0
    next_status_publish = 0.0

    publisher.start()
    source.start()
    logging.info("PowerGateway 0.8.0-dev startet mit Datenquelle tasmota_mqtt")
    try:
        while core.RUNNING:
            now = time.monotonic()
            if now >= next_health_check:
                check_host = str(config.get("lte", {}).get("connection_check_host", "1.1.1.1"))
                status.internet_online = core.internet_available(check_host)
                status.lte_state, status.lte_signal = core.get_lte_status()
                wg_config = config.get("wireguard", {})
                status.wireguard_state = core.get_wireguard_status(
                    str(wg_config.get("interface", "wg0")), bool(wg_config.get("enabled", False))
                )
                next_health_check = now + float(gateway_config.get("health_interval", 30))

            status.mqtt_connected = publisher.connected
            status.meter_connected = source.connected
            if publisher.connected:
                publisher.publish_discovery()
                core.flush_buffer(publisher, message_buffer, int(buffer_config.get("flush_batch_size", 100)))

            reading = source.read()
            if reading is not None:
                values_payload = _normalise_tasmota_reading(reading, gateway_name)
                _atomic_write(LATEST_VALUES_PATH, values_payload)
                encoded = json.dumps(values_payload, separators=(",", ":"), ensure_ascii=False)
                _original_publish_or_buffer(
                    publisher, message_buffer, f"{publisher.topic_prefix}/meter/values", encoded
                )
                status.telegram_count += 1
                status.last_telegram_at = reading.received_at
                status.last_telegram_sha256 = None
                status.last_error = None
                logging.info("Tasmota-Messwerte empfangen: %s", ", ".join(reading.values))

            message_buffer.trim(int(buffer_config.get("max_messages", 10000)))
            status.buffered_messages = message_buffer.count()
            status.updated_at = core.utc_now()
            core.atomic_write_json(status_path, asdict(status))
            if now >= next_status_publish:
                publisher.publish(f"{publisher.topic_prefix}/status", json.dumps(asdict(status)), retain=True)
                next_status_publish = now + float(gateway_config.get("status_interval", 30))
    finally:
        source.stop()
        publisher.stop()
        logging.info("PowerGateway beendet")
    return 0


core.telegram_payload = telegram_payload
core.publish_or_buffer = publish_or_buffer
core.MqttPublisher.publish_discovery = publish_discovery


if __name__ == "__main__":
    try:
        configuration = _load_config()
        source_name = str(configuration.get("meter", {}).get("source", configuration.get("meter", {}).get("mode", "serial"))).lower()
        if source_name in {"tasmota", "tasmota_mqtt", "wifi_tasmota"}:
            raise SystemExit(run_tasmota_source(configuration))
        enable_simulation_if_configured()
        raise SystemExit(core.main())
    except Exception:
        logging.exception("PowerGateway konnte nicht gestartet werden")
        raise SystemExit(1)
