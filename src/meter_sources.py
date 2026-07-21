"""Modulare Datenquellen für PowerGateway.

Jede Quelle liefert normalisierte Messwerte, damit MQTT, Home Assistant,
SQLite und WebGUI unabhängig vom verwendeten Lesekopf bleiben.
"""
from __future__ import annotations

import json
import logging
import queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def nested_value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


@dataclass
class MeterReading:
    source: str
    received_at: str = field(default_factory=utc_now)
    values: dict[str, float | int | str | bool | None] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "received_at": self.received_at,
            "values": self.values,
            "raw": self.raw,
        }


class TasmotaMqttSource:
    """Empfängt Zählerwerte aus einem Tasmota-SENSOR-Topic."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.topic = str(config.get("topic", "tele/Stromzaehler/SENSOR"))
        self.timeout = float(config.get("read_timeout", 2.0))
        self.connected = False
        self._queue: queue.Queue[MeterReading] = queue.Queue(maxsize=100)
        client_id = str(config.get("client_id", "powergateway-tasmota-source"))
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        username = str(config.get("username", ""))
        if username:
            self.client.username_pw_set(username, str(config.get("password", "")))
        if bool(config.get("tls", False)):
            self.client.tls_set(ca_certs=config.get("ca_file") or None)

    @property
    def device_name(self) -> str:
        return f"mqtt://{self.config.get('host', 'localhost')}/{self.topic}"

    def start(self) -> None:
        host = str(self.config.get("host", "localhost"))
        port = int(self.config.get("port", 1883))
        self.client.connect_async(host, port, int(self.config.get("keepalive", 60)))
        self.client.loop_start()
        logging.info("Tasmota-MQTT-Datenquelle startet: %s", self.device_name)

    def stop(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def read(self) -> MeterReading | None:
        try:
            return self._queue.get(timeout=self.timeout)
        except queue.Empty:
            return None

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        del userdata, flags, properties
        self.connected = int(reason_code) == 0
        if self.connected:
            client.subscribe(self.topic, qos=int(self.config.get("qos", 0)))
            logging.info("Tasmota-MQTT verbunden und Topic abonniert: %s", self.topic)
        else:
            logging.warning("Tasmota-MQTT-Verbindung abgelehnt: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        del client, userdata, flags, reason_code, properties
        self.connected = False
        logging.warning("Tasmota-MQTT-Datenquelle getrennt")

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        del client, userdata
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            values = self.parse_payload(payload)
            if not values:
                logging.warning("Tasmota-Nachricht enthält keine konfigurierten Messwerte")
                return
            reading = MeterReading(source="tasmota_mqtt", values=values, raw=payload)
            try:
                self._queue.put_nowait(reading)
            except queue.Full:
                self._queue.get_nowait()
                self._queue.put_nowait(reading)
                logging.warning("Tasmota-Eingangspuffer war voll; ältester Wert wurde verworfen")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logging.warning("Ungültige Tasmota-MQTT-Nachricht: %s", exc)

    def parse_payload(self, payload: dict[str, Any]) -> dict[str, float | int | str | bool | None]:
        mappings = {
            "power_total": str(self.config.get("power_path", "Home.Power_curr")),
            "energy_import": str(self.config.get("energy_import_path", "Home.total_in")),
            "energy_export": str(self.config.get("energy_export_path", "")),
            "voltage_l1": str(self.config.get("voltage_l1_path", "")),
            "voltage_l2": str(self.config.get("voltage_l2_path", "")),
            "voltage_l3": str(self.config.get("voltage_l3_path", "")),
            "current_l1": str(self.config.get("current_l1_path", "")),
            "current_l2": str(self.config.get("current_l2_path", "")),
            "current_l3": str(self.config.get("current_l3_path", "")),
            "frequency": str(self.config.get("frequency_path", "")),
        }
        values: dict[str, float | int | str | bool | None] = {}
        for key, path in mappings.items():
            if not path:
                continue
            value = nested_value(payload, path)
            if value is not None:
                values[key] = value
        return values
