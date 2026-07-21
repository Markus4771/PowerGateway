#!/usr/bin/env python3
"""PowerGateway service entry point."""

from __future__ import annotations

import glob
import logging
import signal
import socket
import sys
import time
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path("/etc/powergateway/config.toml")
RUNNING = True


def stop_service(signum: int, frame: object) -> None:
    global RUNNING
    RUNNING = False


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Konfiguration fehlt: {CONFIG_PATH}")
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def detect_serial_devices() -> list[str]:
    devices: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*"):
        devices.extend(glob.glob(pattern))
    return sorted(dict.fromkeys(devices))


def internet_available(host: str, port: int = 53, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    config = load_config()
    log_level = config.get("gateway", {}).get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, str(log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)

    name = config.get("gateway", {}).get("name", "powergateway")
    logging.info("PowerGateway startet: %s", name)

    last_devices: list[str] = []
    last_online: bool | None = None

    while RUNNING:
        devices = detect_serial_devices()
        if devices != last_devices:
            logging.info("Serielle Geräte: %s", devices or "keine")
            last_devices = devices

        check_host = config.get("lte", {}).get("connection_check_host", "1.1.1.1")
        online = internet_available(str(check_host))
        if online != last_online:
            logging.info("Netzverbindung: %s", "online" if online else "offline")
            last_online = online

        time.sleep(15)

    logging.info("PowerGateway beendet")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("PowerGateway konnte nicht gestartet werden")
        sys.exit(1)
