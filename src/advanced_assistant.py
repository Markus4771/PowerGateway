#!/usr/bin/env python3
"""Erweiterte Assistenten für USB-SML, Home Assistant und Systemdiagnose."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import serial

import powergateway as core
from sml_obis import OBIS_REGISTRY, decode_obis_values

VERSION_PATH = Path(__file__).resolve().parent.parent / "version.txt"
SERVICE_NAMES = (
    "powergateway.service",
    "powergateway-web.service",
    "powergateway-network.service",
    "powergateway-wireguard-apply.service",
)


def project_version() -> str:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip() or "unbekannt"
    except OSError:
        return "unbekannt"


def _resolve_device(device: str) -> str:
    selected = core.resolve_meter_device(device.strip() or "auto")
    if not selected:
        raise ValueError("Kein serieller USB-Lesekopf gefunden.")
    path = Path(selected)
    if not path.exists():
        raise ValueError(f"Serielles Gerät nicht gefunden: {selected}")
    if not os.access(path, os.R_OK):
        raise ValueError(
            f"Keine Leseberechtigung für {selected}. Prüfe die Gruppe dialout und starte das Gerät neu."
        )
    return selected


def serial_probe(device: str = "auto", baudrates: list[int] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    """Testet übliche Baudraten und liefert den ersten vollständigen SML-Frame."""
    selected = _resolve_device(device)
    candidates = baudrates or [9600, 115200, 2400, 300]
    errors: list[str] = []
    started = time.monotonic()
    per_rate = max(1.5, min(4.0, float(timeout) / max(1, len(candidates))))

    for baudrate in candidates:
        chunks: list[bytes] = []
        try:
            with serial.Serial(selected, baudrate=int(baudrate), timeout=0.35) as port:
                deadline = time.monotonic() + per_rate
                while time.monotonic() < deadline:
                    data = port.read(2048)
                    if data:
                        chunks.append(bytes(data))
                        frames = list(core.iter_sml_frames(iter(chunks)))
                        if frames:
                            frame = frames[0]
                            values = [item.to_dict() for item in decode_obis_values(frame)]
                            return {
                                "ok": True,
                                "device": selected,
                                "baudrate": int(baudrate),
                                "frame_length": len(frame),
                                "frame_hex_preview": frame.hex()[:512],
                                "measurements": values,
                                "unknown_obis": [item["obis"] for item in values if not item.get("known", True)],
                                "duration_seconds": round(time.monotonic() - started, 2),
                            }
        except serial.SerialException as exc:
            errors.append(f"{baudrate} Baud: {exc}")
        except OSError as exc:
            errors.append(f"{baudrate} Baud: {exc}")

    detail = "; ".join(errors[-3:]) if errors else "Es wurden Daten gelesen, aber kein vollständiger SML-Frame erkannt."
    raise ValueError(f"Kein gültiges SML-Telegramm empfangen. {detail}")


def _device_info(gateway_name: str) -> dict[str, Any]:
    return {
        "identifiers": [gateway_name],
        "name": gateway_name,
        "manufacturer": "PowerGateway",
        "model": "Modulares Stromzähler-Gateway",
        "sw_version": project_version(),
    }


def discovery_entities(config: dict[str, Any]) -> list[dict[str, Any]]:
    gateway_name = str(config.get("gateway", {}).get("name", "PowerGateway")).strip() or "PowerGateway"
    mqtt_config = config.get("mqtt", {})
    topic_prefix = str(mqtt_config.get("topic_prefix", f"powergateway/{gateway_name}"))
    discovery_prefix = str(mqtt_config.get("discovery_prefix", "homeassistant"))
    device = _device_info(gateway_name)
    entities: list[dict[str, Any]] = []
    published_keys: set[str] = set()
    for definition in OBIS_REGISTRY.values():
        if definition.key in published_keys or definition.diagnostic:
            continue
        payload: dict[str, Any] = {
            "name": definition.name,
            "unique_id": f"{gateway_name}_{definition.key}",
            "state_topic": f"{topic_prefix}/meter/values",
            "value_template": "{{ value_json." + definition.key + " }}",
            "availability_topic": f"{topic_prefix}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        if definition.unit:
            payload["unit_of_measurement"] = definition.unit
        if definition.device_class:
            payload["device_class"] = definition.device_class
        if definition.state_class:
            payload["state_class"] = definition.state_class
        entities.append({
            "key": definition.key,
            "name": definition.name,
            "topic": f"{discovery_prefix}/sensor/{gateway_name}/{definition.key}/config",
            "payload": payload,
        })
        published_keys.add(definition.key)
    return entities


def _mqtt_client(config: dict[str, Any]) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"powergateway-web-{int(time.time())}")
    username = str(config.get("username", "")).strip()
    if username:
        client.username_pw_set(username, str(config.get("password", "")))
    if bool(config.get("tls")):
        client.tls_set(ca_certs=str(config.get("ca_file", "")).strip() or None)
    return client


def publish_discovery(config: dict[str, Any], clear: bool = False, timeout: float = 6.0) -> dict[str, Any]:
    mqtt_config = dict(config.get("mqtt", {}))
    host = str(mqtt_config.get("host", "")).strip()
    if not host:
        raise ValueError("MQTT-Broker ist nicht konfiguriert.")
    port = int(mqtt_config.get("port", 8883 if mqtt_config.get("tls") else 1883))
    entities = discovery_entities(config)
    connected = False
    error = ""
    client = _mqtt_client(mqtt_config)

    def on_connect(current: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        nonlocal connected, error
        del current, userdata, flags, properties
        connected = int(reason_code) == 0
        if not connected:
            error = f"MQTT-Anmeldung abgelehnt: {reason_code}"

    client.on_connect = on_connect
    try:
        client.connect_async(host, port, keepalive=20)
        client.loop_start()
        deadline = time.monotonic() + timeout
        while not connected and not error and time.monotonic() < deadline:
            time.sleep(0.05)
        if not connected:
            raise ValueError(error or "MQTT-Broker antwortet nicht innerhalb des Zeitlimits.")
        for entity in entities:
            payload = "" if clear else json.dumps(entity["payload"], separators=(",", ":"), ensure_ascii=False)
            result = client.publish(entity["topic"], payload, qos=1, retain=True)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise ValueError(f"Discovery konnte nicht veröffentlicht werden: MQTT-Fehler {result.rc}")
        gateway_name = str(config.get("gateway", {}).get("name", "PowerGateway")).strip() or "PowerGateway"
        topic_prefix = str(mqtt_config.get("topic_prefix", f"powergateway/{gateway_name}"))
        if not clear:
            client.publish(f"{topic_prefix}/availability", "online", qos=1, retain=True)
        time.sleep(0.3)
        return {
            "ok": True,
            "count": len(entities),
            "message": (
                f"{len(entities)} Home-Assistant-Discovery-Einträge gelöscht."
                if clear
                else f"{len(entities)} Home-Assistant-Discovery-Einträge veröffentlicht."
            ),
        }
    except (OSError, mqtt.MQTTException) as exc:
        raise ValueError(f"MQTT-Verbindung fehlgeschlagen: {exc}") from exc
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        client.loop_stop()


def service_diagnostics(lines: int = 80) -> dict[str, Any]:
    statuses: list[dict[str, str]] = []
    for service in SERVICE_NAMES:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service], capture_output=True, text=True, timeout=4, check=False
            )
            state = (result.stdout or result.stderr).strip() or "unbekannt"
        except (OSError, subprocess.TimeoutExpired) as exc:
            state = f"nicht prüfbar: {exc}"
        statuses.append({"service": service, "state": state})

    command = ["journalctl", "--no-pager", "-n", str(max(10, min(int(lines), 300)))]
    for service in SERVICE_NAMES[:3]:
        command.extend(["-u", service])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        logs = (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        logs = f"Protokolle konnten nicht gelesen werden: {exc}"
    if not logs:
        logs = "Keine Protokolle verfügbar. Der Benutzer powergateway benötigt gegebenenfalls Leserechte für das Journal."
    return {"services": statuses, "logs": logs[-60000:]}
