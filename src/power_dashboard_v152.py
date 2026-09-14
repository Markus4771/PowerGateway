#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from flask import Response, jsonify
import energy_history

app = energy_history.app
legacy = energy_history.legacy
DATA_DIR = Path('/var/lib/powergateway')
LATEST_FILE = DATA_DIR / 'latest_values.json'
STATUS_FILE = DATA_DIR / 'status.json'

for key in ('power_total', '1-0:16.7.0*255'):
    if key not in energy_history.POWER_KEYS:
        energy_history.POWER_KEYS = (*energy_history.POWER_KEYS, key)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ('value', 'reading', 'wert'):
            if key in value:
                return _number(value[key])
        return None
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _find(data: Any) -> float | None:
    wanted = {'power_total', 'power_w', 'power', 'active_power', '1-0:16.7.0', '1-0:16.7.0*255'}
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in wanted:
                number = _number(value)
                if number is not None:
                    return number
        for nested in ('values', 'last_measurement', 'measurement', 'measurements'):
            found = _find(data.get(nested))
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                key = str(item.get('key') or item.get('obis') or '').lower()
                if key in wanted:
                    number = _number(item.get('value'))
                    if number is not None:
                        return number
    return None


@app.get('/_internal/power/live')
@legacy.login_required
def live_power() -> Response:
    latest = _read(LATEST_FILE)
    value = _find(latest)
    source = 'latest_values.json'
    received_at = latest.get('received_at') or latest.get('captured_at')
    if value is None:
        status = _read(STATUS_FILE)
        value = _find(status)
        source = 'status.json'
        received_at = status.get('measurement_received_at') or status.get('last_message_at') or status.get('updated_at')
    return jsonify({'ok': value is not None, 'power_w': value, 'source': source, 'received_at': received_at, 'obis': '1-0:16.7.0*255'})
