#!/usr/bin/env python3
"""PowerGateway service.

Reads SML telegrams from an optical USB reader, publishes them through MQTT,
buffers messages while offline and writes a machine-readable status file.
"""

from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

import paho.mqtt.client as mqtt
import serial

CONFIG_PATH = Path(os.environ.get("POWERGATEWAY_CONFIG", "/etc/powergateway/config.toml"))
RUNNING = True
SML_START = bytes.fromhex("1b1b1b1b01010101")
SML_END = bytes.fromhex("1b1b1b1b1a")


@dataclass
class GatewayStatus:
    version: str = "0.2.0-dev"
    started_at: str = ""
    updated_at: str = ""
    meter_device: str | None = None
    meter_connected: bool = False
    last_telegram_at: str | None = None
    last_telegram_sha256: str | None = None
    telegram_count: int = 0
    internet_online: bool = False
    mqtt_connected: bool = False
    buffered_messages: int = 0
    lte_state: str = "unknown"
    lte_signal: str | None = None
    wireguard_state: str = "disabled"
    last_error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stop_service(signum: int, frame: object) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Konfiguration fehlt: {CONFIG_PATH}")
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def detect_serial_devices() -> list[str]:
    devices: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        devices.extend(glob.glob(pattern))
    return sorted(dict.fromkeys(devices))


def resolve_meter_device(configured: str) -> str | None:
    if configured and configured != "auto":
        return configured if Path(configured).exists() else None
    devices = detect_serial_devices()
    by_id = [item for item in devices if item.startswith("/dev/serial/by-id/")]
    return (by_id or devices or [None])[0]


def internet_available(host: str, port: int = 53, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_command(command: list[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def get_lte_status() -> tuple[str, str | None]:
    output = run_command(["mmcli", "-L"])
    if not output or "No modems were found" in output:
        return "not_found", None
    modem_path = next((token for token in output.split() if token.startswith("/org/freedesktop/ModemManager1/Modem/")), "")
    if not modem_path:
        return "detected", None
    details = run_command(["mmcli", "-m", modem_path.rsplit("/", 1)[-1], "-K"])
    state = "connected" if "modem.generic.state : connected" in details else "detected"
    signal = None
    for line in details.splitlines():
        if "modem.generic.signal-quality.value" in line:
            signal = line.split(":", 1)[-1].strip()
            break
    return state, signal


def get_wireguard_status(interface: str, enabled: bool) -> str:
    if not enabled:
        return "disabled"
    output = run_command(["wg", "show", interface])
    if not output:
        return "down"
    return "active" if "interface:" in output or "peer:" in output else "down"


def iter_sml_frames(chunks: Iterator[bytes], max_frame_size: int = 65536) -> Iterator[bytes]:
    """Extract complete SML transport frames from arbitrary serial chunks."""
    buffer = bytearray()
    for chunk in chunks:
        if not chunk:
            continue
        buffer.extend(chunk)
        while True:
            start = buffer.find(SML_START)
            if start < 0:
                if len(buffer) > len(SML_START):
                    del buffer[:-len(SML_START)]
                break
            if start:
                del buffer[:start]
            end = buffer.find(SML_END, len(SML_START))
            if end < 0:
                if len(buffer) > max_frame_size:
                    logging.warning("Verwerfe übergroßen unvollständigen SML-Frame")
                    buffer.clear()
                break
            # End marker is followed by fill byte and two-byte CRC in standard SML.
            frame_end = end + len(SML_END) + 3
            if len(buffer) < frame_end:
                break
            yield bytes(buffer[:frame_end])
            del buffer[:frame_end]


def serial_chunks(port: serial.Serial, chunk_size: int = 1024) -> Iterator[bytes]:
    while RUNNING and port.is_open:
        data = port.read(chunk_size)
        if data:
            yield data


class MessageBuffer:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS queue ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, "
            "payload TEXT NOT NULL, qos INTEGER NOT NULL, retain INTEGER NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def add(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
        self.connection.execute(
            "INSERT INTO queue(topic,payload,qos,retain,created_at) VALUES(?,?,?,?,?)",
            (topic, payload, qos, int(retain), utc_now()),
        )
        self.connection.commit()

    def pending(self, limit: int = 100) -> list[tuple[int, str, str, int, bool]]:
        rows = self.connection.execute(
            "SELECT id,topic,payload,qos,retain FROM queue ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), int(r[3]), bool(r[4])) for r in rows]

    def remove(self, row_id: int) -> None:
        self.connection.execute("DELETE FROM queue WHERE id=?", (row_id,))
        self.connection.commit()

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0])

    def trim(self, maximum: int) -> None:
        excess = self.count() - maximum
        if excess > 0:
            self.connection.execute(
                "DELETE FROM queue WHERE id IN (SELECT id FROM queue ORDER BY id LIMIT ?)",
                (excess,),
            )
            self.connection.commit()


class MqttPublisher:
    def __init__(self, config: dict[str, Any], gateway_name: str) -> None:
        self.config = config
        self.gateway_name = gateway_name
        self.enabled = bool(config.get("enabled", False))
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=gateway_name)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        username = str(config.get("username", ""))
        if username:
            self.client.username_pw_set(username, str(config.get("password", "")))
        if bool(config.get("tls", False)):
            self.client.tls_set(ca_certs=config.get("ca_file") or None)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        del client, userdata, flags, properties
        self.connected = int(reason_code) == 0
        logging.info("MQTT verbunden" if self.connected else "MQTT-Verbindung abgelehnt: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        del client, userdata, flags, reason_code, properties
        self.connected = False
        logging.warning("MQTT getrennt")

    def start(self) -> None:
        if not self.enabled:
            return
        self.client.will_set(f"{self.topic_prefix}/availability", "offline", qos=1, retain=True)
        self.client.connect_async(str(self.config["host"]), int(self.config.get("port", 1883)), 60)
        self.client.loop_start()

    @property
    def topic_prefix(self) -> str:
        return str(self.config.get("topic_prefix", f"powergateway/{self.gateway_name}"))

    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        if not self.enabled or not self.connected:
            return False
        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def publish_discovery(self) -> None:
        if not self.connected or not bool(self.config.get("homeassistant_discovery", True)):
            return
        base = str(self.config.get("discovery_prefix", "homeassistant"))
        device = {
            "identifiers": [self.gateway_name],
            "name": self.gateway_name,
            "manufacturer": "PowerGateway",
            "model": "Raspberry Pi Meter Gateway",
            "sw_version": "0.2.0-dev",
        }
        sensors = {
            "telegram_count": ("Telegramme", None, "mdi:counter"),
            "buffered_messages": ("Gepufferte Nachrichten", None, "mdi:database-clock"),
            "internet_online": ("Internet", None, "mdi:wan"),
            "lte_signal": ("LTE Signal", "%", "mdi:signal"),
        }
        for key, (name, unit, icon) in sensors.items():
            payload: dict[str, Any] = {
                "name": name,
                "unique_id": f"{self.gateway_name}_{key}",
                "state_topic": f"{self.topic_prefix}/status",
                "value_template": "{{ value_json." + key + " }}",
                "availability_topic": f"{self.topic_prefix}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": icon,
                "device": device,
            }
            if unit:
                payload["unit_of_measurement"] = unit
            self.publish(f"{base}/sensor/{self.gateway_name}/{key}/config", json.dumps(payload), retain=True)
        self.publish(f"{self.topic_prefix}/availability", "online", retain=True)

    def stop(self) -> None:
        if self.enabled:
            if self.connected:
                self.publish(f"{self.topic_prefix}/availability", "offline", retain=True)
            self.client.disconnect()
            self.client.loop_stop()


def telegram_payload(frame: bytes, gateway_name: str) -> dict[str, Any]:
    return {
        "gateway": gateway_name,
        "received_at": utc_now(),
        "protocol": "sml",
        "length": len(frame),
        "sha256": hashlib.sha256(frame).hexdigest(),
        "raw_hex": frame.hex(),
    }


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def publish_or_buffer(publisher: MqttPublisher, buffer: MessageBuffer, topic: str, payload: str) -> None:
    if not publisher.publish(topic, payload):
        buffer.add(topic, payload)


def flush_buffer(publisher: MqttPublisher, buffer: MessageBuffer, batch_size: int) -> int:
    if not publisher.connected:
        return 0
    sent = 0
    for row_id, topic, payload, qos, retain in buffer.pending(batch_size):
        if not publisher.publish(topic, payload, qos, retain):
            break
        buffer.remove(row_id)
        sent += 1
    return sent


def main() -> int:
    config = load_config()
    gateway_config = config.get("gateway", {})
    logging.basicConfig(
        level=getattr(logging, str(gateway_config.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)

    gateway_name = str(gateway_config.get("name", "powergateway"))
    status_path = Path(str(gateway_config.get("status_path", "/var/lib/powergateway/status.json")))
    meter_config = config.get("meter", {})
    buffer_config = config.get("buffer", {})
    message_buffer = MessageBuffer(str(buffer_config.get("path", "/var/lib/powergateway/buffer.db")))
    publisher = MqttPublisher(config.get("mqtt", {}), gateway_name)
    publisher.start()

    status = GatewayStatus(started_at=utc_now(), updated_at=utc_now())
    logging.info("PowerGateway %s startet: %s", status.version, gateway_name)
    serial_port: serial.Serial | None = None
    frames: Iterator[bytes] | None = None
    next_health_check = 0.0
    next_status_publish = 0.0

    try:
        while RUNNING:
            now = time.monotonic()
            if now >= next_health_check:
                check_host = str(config.get("lte", {}).get("connection_check_host", "1.1.1.1"))
                status.internet_online = internet_available(check_host)
                status.lte_state, status.lte_signal = get_lte_status()
                wg_config = config.get("wireguard", {})
                status.wireguard_state = get_wireguard_status(
                    str(wg_config.get("interface", "wg0")), bool(wg_config.get("enabled", False))
                )
                next_health_check = now + float(gateway_config.get("health_interval", 30))

            status.mqtt_connected = publisher.connected
            if publisher.connected:
                publisher.publish_discovery()
                flushed = flush_buffer(publisher, message_buffer, int(buffer_config.get("flush_batch_size", 100)))
                if flushed:
                    logging.info("%d gepufferte Nachrichten übertragen", flushed)

            if serial_port is None or not serial_port.is_open:
                device = resolve_meter_device(str(meter_config.get("device", "auto")))
                status.meter_device = device
                status.meter_connected = False
                if device:
                    try:
                        serial_port = serial.Serial(
                            device,
                            baudrate=int(meter_config.get("baudrate", 9600)),
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE,
                            timeout=float(meter_config.get("read_timeout", 1.0)),
                        )
                        frames = iter_sml_frames(serial_chunks(serial_port))
                        status.meter_connected = True
                        status.last_error = None
                        logging.info("IR-Lesekopf geöffnet: %s", device)
                    except (OSError, serial.SerialException) as exc:
                        status.last_error = str(exc)
                        logging.warning("IR-Lesekopf kann nicht geöffnet werden: %s", exc)
                        serial_port = None
                        time.sleep(float(meter_config.get("reconnect_interval", 10)))
                else:
                    status.last_error = "Kein serielles Gerät gefunden"
                    time.sleep(float(meter_config.get("reconnect_interval", 10)))
            else:
                try:
                    assert frames is not None
                    frame = next(frames)
                    payload_data = telegram_payload(frame, gateway_name)
                    payload = json.dumps(payload_data, separators=(",", ":"))
                    publish_or_buffer(publisher, message_buffer, f"{publisher.topic_prefix}/meter/raw", payload)
                    status.telegram_count += 1
                    status.last_telegram_at = str(payload_data["received_at"])
                    status.last_telegram_sha256 = str(payload_data["sha256"])
                    status.last_error = None
                    logging.info("SML-Telegramm empfangen: %d Bytes", len(frame))
                except StopIteration:
                    serial_port = None
                    frames = None
                except (OSError, serial.SerialException) as exc:
                    status.last_error = str(exc)
                    status.meter_connected = False
                    logging.warning("Serielle Verbindung unterbrochen: %s", exc)
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                    serial_port = None
                    frames = None

            message_buffer.trim(int(buffer_config.get("max_messages", 10000)))
            status.buffered_messages = message_buffer.count()
            status.updated_at = utc_now()
            atomic_write_json(status_path, asdict(status))

            if now >= next_status_publish:
                publisher.publish(f"{publisher.topic_prefix}/status", json.dumps(asdict(status)), retain=True)
                next_status_publish = now + float(gateway_config.get("status_interval", 30))
    finally:
        if serial_port is not None:
            serial_port.close()
        publisher.stop()
        logging.info("PowerGateway beendet")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("PowerGateway konnte nicht gestartet werden")
        sys.exit(1)
