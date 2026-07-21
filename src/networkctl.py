#!/usr/bin/env python3
"""Apply PowerGateway network configuration through NetworkManager."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from network_manager import apply_priorities, configure_lte, configure_wifi, snapshot

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path("/etc/powergateway/config.toml")
STATUS_PATH = Path("/var/lib/powergateway/network_status.json")


def load_config() -> dict:
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def write_status(config: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot(config).to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATUS_PATH)


def apply(config: dict) -> int:
    network = config.get("network", {})
    wifi = network.get("wifi", {})
    lte = network.get("lte", {})

    if bool(wifi.get("enabled", False)) and str(wifi.get("ssid", "")).strip():
        configure_wifi(
            str(wifi.get("ssid", "")),
            str(wifi.get("password", "")),
            str(wifi.get("connection", "PowerGateway-WLAN")),
        )
    if bool(lte.get("enabled", False)) and str(lte.get("apn", "")).strip():
        configure_lte(
            str(lte.get("apn", "")),
            str(lte.get("connection", "PowerGateway-LTE")),
            str(lte.get("username", "")),
            str(lte.get("password", "")),
        )

    for message in apply_priorities(config):
        logging.info(message)
    write_status(config)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "apply":
        return apply(config)
    write_status(config)
    print(json.dumps(snapshot(config).to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
