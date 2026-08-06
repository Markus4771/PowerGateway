#!/usr/bin/env python3
"""Dekodierte SML-Livewerte in Status, Dashboard und Historie bereitstellen.

Der historische Kerndienst veröffentlicht bislang nur das rohe SML-Telegramm.
Dieses Laufzeitmodul ergänzt den vorhandenen Dienst ohne doppelte serielle
Portzugriffe: Jedes bereits empfangene Frame wird dekodiert und atomar als
``latest_values.json`` sowie im normalen ``status.json`` abgelegt.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from sml_obis import decode_obis_values

DATA_DIR = Path('/var/lib/powergateway')
LATEST_VALUES_FILE = DATA_DIR / 'latest_values.json'
_INSTALLED = False
_LATEST: dict[str, Any] = {}


def _measurement_payload(frame: bytes, base: dict[str, Any]) -> dict[str, Any]:
    measurements = [item.to_dict() for item in decode_obis_values(frame)]
    values = {str(item['key']): item.get('value') for item in measurements}
    result: dict[str, Any] = {
        'updated_at': int(time.time()),
        'received_at': base.get('received_at'),
        'protocol': 'sml',
        'source': 'usb_sml',
        'measurements': measurements,
        'values': values,
    }
    # Direkte Schlüssel bleiben für ältere Dashboard- und Historienmodule
    # erhalten. Insbesondere power_total wird als aktuelle Leistung verwendet.
    result.update(values)
    return result


def install(core: Any) -> None:
    """Installiert die Laufzeiterweiterung genau einmal in ``powergateway``."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_telegram_payload: Callable[[bytes, str], dict[str, Any]] = core.telegram_payload
    original_atomic_write: Callable[[Path, dict[str, Any]], None] = core.atomic_write_json

    def telegram_payload(frame: bytes, gateway_name: str) -> dict[str, Any]:
        global _LATEST
        payload = original_telegram_payload(frame, gateway_name)
        live = _measurement_payload(frame, payload)
        payload['measurements'] = live['measurements']
        payload['values'] = live['values']
        payload.update(live['values'])
        _LATEST = live
        original_atomic_write(LATEST_VALUES_FILE, live)
        return payload

    def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
        if path.name == 'status.json' and _LATEST:
            enriched = dict(data)
            enriched['last_measurement'] = dict(_LATEST.get('values', {}))
            enriched['measurements'] = list(_LATEST.get('measurements', []))
            enriched['last_measurement_at'] = _LATEST.get('received_at')
            # Direkte Felder erleichtern die Abwärtskompatibilität der WebGUI.
            enriched.update(_LATEST.get('values', {}))
            data = enriched
        original_atomic_write(path, data)

    core.telegram_payload = telegram_payload
    core.atomic_write_json = atomic_write_json
