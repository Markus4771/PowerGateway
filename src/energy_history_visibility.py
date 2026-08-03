#!/usr/bin/env python3
"""Historische Messwerte sichtbar halten, ohne Zähler-Reset-Berechnungen zu verändern."""
from __future__ import annotations

from typing import Any

import energy_history

_original_history = energy_history.history


def _all_points(start: int, end: int, bucket: int) -> list[dict[str, Any]]:
    """Lädt die komplette Zeitreihe unabhängig vom Berechnungs-Reset."""
    with energy_history._connect() as db:
        rows = db.execute(
            '''SELECT (ts / ?) * ? bucket,
                      AVG(power_w) power_w,
                      MIN(energy_kwh) energy_min,
                      MAX(energy_kwh) energy_max,
                      AVG(voltage_v) voltage_v,
                      AVG(current_a) current_a,
                      AVG(frequency_hz) frequency_hz,
                      AVG(power_factor) power_factor,
                      COUNT(*) samples
                 FROM measurements
                WHERE ts BETWEEN ? AND ?
                GROUP BY bucket ORDER BY bucket''',
            (bucket, bucket, start, end),
        ).fetchall()

    return [
        {
            'ts': int(row['bucket']),
            'power_w': row['power_w'],
            'energy_kwh': (
                row['energy_max'] - row['energy_min']
                if row['energy_min'] is not None and row['energy_max'] is not None
                else None
            ),
            'voltage_v': row['voltage_v'],
            'current_a': row['current_a'],
            'frequency_hz': row['frequency_hz'],
            'power_factor': row['power_factor'],
            'samples': int(row['samples'] or 0),
        }
        for row in rows
    ]


def history_with_visible_archive(name: str) -> dict[str, Any]:
    result = _original_history(name)
    requested_start = int(result.get('requested_start', result.get('start', 0)) or 0)
    end = int(result.get('end', 0) or 0)
    bucket = max(1, int(result.get('bucket_seconds', 60) or 60))
    calculation_start = int(result.get('start', requested_start) or requested_start)

    if requested_start > 0 and end > requested_start:
        result['points'] = _all_points(requested_start, end, bucket)
        result['start'] = requested_start

    result['calculation_start'] = calculation_start
    result['history_includes_pre_reset_values'] = calculation_start > requested_start
    return result


energy_history.history = history_with_visible_archive
