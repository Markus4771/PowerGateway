#!/usr/bin/env python3
"""Robuster One-shot-Sammler für die PowerGateway-Energiehistorie.

Der Sammler übernimmt bevorzugt die vom Hauptdienst geschriebenen Livewerte aus
``latest_values.json``. Ältere Installationen mit Messwerten in ``status.json``
bleiben über ``energy_history.sample()`` kompatibel.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import energy_history

LATEST_VALUES_FILE = Path('/var/lib/powergateway/latest_values.json')


def _read_latest_values() -> dict[str, Any]:
    try:
        value = json.loads(LATEST_VALUES_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _find_measurement(data: dict[str, Any], key: str) -> float | None:
    direct = _number(data.get(key))
    if direct is not None:
        return direct
    measurements = data.get('measurements')
    if isinstance(measurements, list):
        for item in measurements:
            if isinstance(item, dict) and item.get('key') == key:
                return _number(item.get('value'))
    return None


def _sample_latest_values() -> dict[str, Any]:
    data = _read_latest_values()
    if not data:
        return {'ok': False, 'message': 'latest_values.json fehlt oder ist ungültig.'}

    values = {
        'power_w': _find_measurement(data, 'power_total'),
        'energy_kwh': _find_measurement(data, 'energy_import'),
        'voltage_v': _find_measurement(data, 'voltage'),
        'current_a': _find_measurement(data, 'current'),
        'frequency_hz': _find_measurement(data, 'frequency'),
        'power_factor': _find_measurement(data, 'power_factor'),
    }
    if values['power_w'] is None and values['energy_kwh'] is None:
        return {
            'ok': False,
            'message': 'latest_values.json enthält weder power_total noch energy_import.',
            'available_keys': sorted(data.keys()),
        }

    ts = int(time.time())
    with energy_history._connect() as db:
        db.execute(
            '''INSERT OR REPLACE INTO measurements
               (ts,power_w,energy_kwh,voltage_v,current_a,frequency_hz,power_factor)
               VALUES (?,?,?,?,?,?,?)''',
            (
                ts,
                values['power_w'],
                values['energy_kwh'],
                values['voltage_v'],
                values['current_a'],
                values['frequency_hz'],
                values['power_factor'],
            ),
        )
    return {
        'ok': True,
        'status': 'stored',
        'source': 'latest_values.json',
        'timestamp': ts,
        **values,
    }


def main() -> int:
    # Datenbank und Schema immer anlegen, auch bevor der erste Messwert da ist.
    with energy_history._connect():
        pass

    result = _sample_latest_values()
    if not result.get('ok'):
        # Abwärtskompatibilität für ältere Datenformate.
        fallback = energy_history.sample()
        result = fallback if fallback.get('ok') else {
            'ok': True,
            'status': 'waiting',
            'message': result.get('message') or fallback.get('message') or 'Noch keine Messwerte vorhanden.',
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
