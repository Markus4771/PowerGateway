#!/usr/bin/env python3
"""Startet den bestehenden Dienst mit zusammengeführter Laufzeitkonfiguration."""
from __future__ import annotations

import logging

import powergateway as core
import service
import sml_live_runtime
from runtime_config import merged_config


def load_config() -> dict:
    with core.CONFIG_PATH.open("rb") as handle:
        base = service.tomllib.load(handle)
    return merged_config(base)


def main() -> int:
    configuration = load_config()
    service._load_config = lambda: configuration
    core.load_config = lambda: configuration
    source_name = str(
        configuration.get("meter", {}).get(
            "source", configuration.get("meter", {}).get("mode", "serial")
        )
    ).lower()
    if source_name in {"tasmota", "tasmota_mqtt", "wifi_tasmota"}:
        return service.run_tasmota_source(configuration)
    service.enable_simulation_if_configured()
    # Ein bereits empfangenes SML-Frame wird genau einmal dekodiert und für
    # Dashboard, Statusdatei und Energiehistorie bereitgestellt. Der serielle
    # Port wird weiterhin ausschließlich vom Hauptdienst geöffnet.
    sml_live_runtime.install(core)
    return core.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("PowerGateway konnte nicht gestartet werden")
        raise SystemExit(1)
