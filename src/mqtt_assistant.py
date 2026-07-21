#!/usr/bin/env python3
"""MQTT-Prüfung und Nachrichtenerkennung für die PowerGateway-WebGUI."""
from __future__ import annotations

import json
import ssl
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt


@dataclass
class Capture:
    connected: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    error: str = ""
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)


def _client(config: dict[str, Any], capture: Capture) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"powergateway-assistant-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv311,
    )
    username = str(config.get("username", "")).strip()
    if username:
        client.username_pw_set(username, str(config.get("password", "")))
    if bool(config.get("tls")):
        ca_file = str(config.get("ca_file", "")).strip() or None
        client.tls_set(ca_certs=ca_file, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

    def on_connect(current: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if int(reason_code) == 0:
            capture.connected.set()
        else:
            capture.error = f"MQTT-Anmeldung abgelehnt: {reason_code}"
            capture.finished.set()

    def on_disconnect(current: mqtt.Client, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        if not capture.connected.is_set() and not capture.error:
            capture.error = f"MQTT-Verbindung getrennt: {reason_code}"
            capture.finished.set()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


def _validated(config: dict[str, Any]) -> tuple[str, int]:
    host = str(config.get("host", "")).strip()
    if not host:
        raise ValueError("Broker-Adresse fehlt.")
    try:
        port = int(config.get("port", 8883 if config.get("tls") else 1883))
    except (TypeError, ValueError) as exc:
        raise ValueError("Ungültiger MQTT-Port.") from exc
    if port < 1 or port > 65535:
        raise ValueError("Ungültiger MQTT-Port.")
    return host, port


def connection_test(config: dict[str, Any], timeout: float = 6.0) -> dict[str, Any]:
    host, port = _validated(config)
    capture = Capture()
    client = _client(config, capture)
    try:
        client.connect_async(host, port, keepalive=15)
        client.loop_start()
        if not capture.connected.wait(timeout):
            raise ValueError(capture.error or "Keine MQTT-Verbindung innerhalb des Zeitlimits.")
        return {"ok": True, "message": f"MQTT-Verbindung zu {host}:{port} erfolgreich."}
    except (OSError, mqtt.MQTTException) as exc:
        raise ValueError(f"MQTT-Verbindung fehlgeschlagen: {exc}") from exc
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        client.loop_stop()


def capture_messages(
    config: dict[str, Any], topic_filter: str = "#", timeout: float = 8.0, max_messages: int = 100
) -> list[dict[str, Any]]:
    host, port = _validated(config)
    topic_filter = topic_filter.strip() or "#"
    capture = Capture()
    client = _client(config, capture)

    def on_connect(current: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if int(reason_code) != 0:
            capture.error = f"MQTT-Anmeldung abgelehnt: {reason_code}"
            capture.finished.set()
            return
        capture.connected.set()
        current.subscribe(topic_filter, qos=0)

    def on_message(current: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        raw = bytes(message.payload)
        text = raw.decode("utf-8", errors="replace")
        parsed: Any = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pass
        capture.messages[message.topic] = {
            "topic": message.topic,
            "payload": text[:65536],
            "json": parsed,
            "retained": bool(message.retain),
            "received_at": int(time.time()),
        }
        if len(capture.messages) >= max_messages:
            capture.finished.set()

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect_async(host, port, keepalive=20)
        client.loop_start()
        if not capture.connected.wait(6.0):
            raise ValueError(capture.error or "Broker wurde nicht verbunden.")
        capture.finished.wait(max(1.0, min(float(timeout), 20.0)))
        return sorted(capture.messages.values(), key=lambda item: item["topic"])
    except (OSError, mqtt.MQTTException) as exc:
        raise ValueError(f"MQTT-Empfang fehlgeschlagen: {exc}") from exc
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        client.loop_stop()


def flatten_json(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.extend(flatten_json(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value[:20]):
            path = f"{prefix}.{index}" if prefix else str(index)
            result.extend(flatten_json(child, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result.append({"path": prefix, "value": value, "suggestion": _suggest(prefix)})
    return result


def _suggest(path: str) -> str:
    name = path.lower().replace("-", "_")
    if any(token in name for token in ("power_curr", "power_total", "leistung", "watts", "power")):
        return "power"
    if any(token in name for token in ("total_in", "energy_import", "import", "bezug", "1_8_0")):
        return "energy_import"
    if any(token in name for token in ("total_out", "energy_export", "export", "einspeis", "2_8_0")):
        return "energy_export"
    return ""
