#!/usr/bin/env python3
"""Privileged PowerGateway network controller.

The web application writes the desired network configuration to
``/var/lib/powergateway/network_config.json``. This daemon applies changes via
NetworkManager and continuously maintains the automatic setup hotspot.
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

from network_manager import (
    apply_priorities,
    configure_hotspot,
    configure_lan,
    configure_lte,
    configure_wifi,
    snapshot,
    stop_hotspot,
)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

CONFIG_PATH = Path("/etc/powergateway/config.toml")
WEB_CONFIG_PATH = Path("/var/lib/powergateway/network_config.json")
STATUS_PATH = Path("/var/lib/powergateway/network_status.json")
RESULT_PATH = Path("/var/lib/powergateway/network_result.json")
_STOP = False


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def load_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("rb") as handle:
            config: dict[str, Any] = tomllib.load(handle)
    except (OSError, ValueError):
        config = {}
    web_network = _read_json(WEB_CONFIG_PATH)
    if web_network:
        config["network"] = web_network
    return config


def write_status(config: dict[str, Any]) -> dict[str, Any]:
    value = snapshot(config).to_dict()
    value["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_json(STATUS_PATH, value)
    return value


def _record(ok: bool, messages: list[str], error: str = "") -> None:
    _atomic_json(RESULT_PATH, {
        "ok": ok,
        "messages": messages,
        "error": error,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def apply(config: dict[str, Any]) -> bool:
    network = config.get("network", {})
    messages: list[str] = []
    hotspot = network.get("hotspot", {})
    hotspot_connection = str(hotspot.get("connection", "PowerGateway-Setup"))

    # A WLAN adapter normally cannot reliably remain client and access point at
    # the same time. Stop the setup AP before trying a configured WLAN client.
    stop_hotspot(hotspot_connection)

    actions = (
        ("LAN", network.get("lan", {}), configure_lan),
        ("WLAN", network.get("wifi", {}), configure_wifi),
        ("LTE", network.get("lte", {}), configure_lte),
    )
    for title, section, handler in actions:
        if not bool(section.get("enabled", False)):
            messages.append(f"{title}: deaktiviert")
            continue
        if title == "WLAN" and not str(section.get("ssid", "")).strip():
            messages.append("WLAN: keine SSID konfiguriert")
            continue
        if title == "LTE" and not str(section.get("apn", "")).strip():
            messages.append("LTE: kein APN konfiguriert")
            continue
        result = handler(section)
        text = result.output or result.error or ("erfolgreich" if result.ok else "fehlgeschlagen")
        messages.append(f"{title}: {text}")
        if not result.ok and title == "LAN":
            logging.warning("LAN-Konfiguration fehlgeschlagen: %s", result.error)

    messages.extend(apply_priorities(config))
    maintain_hotspot(config, messages)
    write_status(config)
    _record(True, messages)
    return True


def maintain_hotspot(config: dict[str, Any], messages: list[str] | None = None) -> None:
    network = config.get("network", {})
    section = network.get("hotspot", {})
    mode = str(section.get("mode", "auto")).lower()
    connection = str(section.get("connection", "PowerGateway-Setup"))
    current = snapshot(config)
    wifi_connected = current.wifi is not None and current.wifi.state == "connected"
    alternative_uplink = any(
        link is not None and link.state == "connected"
        for link in (current.lan, current.lte)
    )
    offline_fallback = bool(section.get("offline_fallback", True))
    should_run = mode == "always" or (mode == "auto" and not wifi_connected and (alternative_uplink or offline_fallback))
    if mode == "off":
        should_run = False

    if should_run and not current.hotspot_active:
        result = configure_hotspot(section)
        if messages is not None:
            messages.append("Hotspot: " + (result.output or result.error or ("gestartet" if result.ok else "fehlgeschlagen")))
    elif not should_run and current.hotspot_active:
        result = stop_hotspot(connection)
        if messages is not None:
            messages.append("Hotspot: " + (result.output or result.error or "beendet"))


def daemon() -> int:
    logging.info("Netzwerkdienst gestartet")
    last_mtime = -1.0
    while not _STOP:
        config = load_config()
        try:
            mtime = WEB_CONFIG_PATH.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime != last_mtime:
            try:
                apply(config)
            except Exception as exc:  # keep connectivity controller alive
                logging.exception("Netzwerkkonfiguration konnte nicht angewendet werden")
                _record(False, [], str(exc))
            last_mtime = mtime
        try:
            maintain_hotspot(config)
            write_status(config)
        except Exception:
            logging.exception("Netzwerkstatus konnte nicht aktualisiert werden")
        time.sleep(5)
    return 0


def _stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    command = sys.argv[1] if len(sys.argv) > 1 else "daemon"
    config = load_config()
    if command == "apply":
        return 0 if apply(config) else 1
    if command == "status":
        print(json.dumps(write_status(config), indent=2, ensure_ascii=False))
        return 0
    return daemon()


if __name__ == "__main__":
    raise SystemExit(main())
