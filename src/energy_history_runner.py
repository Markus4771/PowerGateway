#!/usr/bin/env python3
"""Dauerhafter Sammler für die PowerGateway-Energiehistorie."""
from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any

import energy_history

LATEST_VALUES_FILE = Path('/var/lib/powergateway/latest_values.json')
STATE_FILE = Path('/var/lib/powergateway/energy_collector_state.json')
ALLOWED_INTERVALS = (5, 10, 30, 60)
DEFAULT_INTERVAL = 10
_stop_requested = False


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


def _sample_interval() -> int:
    settings = energy_history._settings()
    try:
        interval = int(settings.get('sample_interval_seconds', DEFAULT_INTERVAL))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL
    return interval if interval in ALLOWED_INTERVALS else DEFAULT_INTERVAL


def _write_state(result: dict[str, Any], interval: int) -> None:
    state = {
        'updated_at': int(time.time()),
        'sample_interval_seconds': interval,
        'last_result': result,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(STATE_FILE)


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


def sample_once() -> dict[str, Any]:
    result = _sample_latest_values()
    if not result.get('ok'):
        fallback = energy_history.sample()
        result = fallback if fallback.get('ok') else {
            'ok': True,
            'status': 'waiting',
            'message': result.get('message') or fallback.get('message') or 'Noch keine Messwerte vorhanden.',
        }
    return result


def _request_stop(_signum: int, _frame: object) -> None:
    global _stop_requested
    _stop_requested = True


def run_daemon() -> int:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    print(json.dumps({'ok': True, 'status': 'started', 'interval': _sample_interval()}, ensure_ascii=False), flush=True)

    while not _stop_requested:
        started = time.monotonic()
        interval = _sample_interval()
        result = sample_once()
        _write_state(result, interval)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        deadline = time.monotonic() + max(0.0, interval - (time.monotonic() - started))
        while not _stop_requested and time.monotonic() < deadline:
            time.sleep(min(0.5, deadline - time.monotonic()))

    print(json.dumps({'ok': True, 'status': 'stopped'}, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--daemon', action='store_true', help='Messwerte dauerhaft im konfigurierten Intervall erfassen')
    args = parser.parse_args()

    with energy_history._connect():
        pass
    if args.daemon:
        return run_daemon()

    result = sample_once()
    _write_state(result, _sample_interval())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
