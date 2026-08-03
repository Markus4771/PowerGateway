#!/usr/bin/env python3
"""Phase 4: adaptive Diagrammauflösung mit 10-Sekunden-Ansicht für einen Tag."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import energy_analysis_phase3 as previous
import energy_history

app = previous.app
legacy = previous.legacy
runtime = previous.runtime

# Ein voller Tag wird ausdrücklich in 10-Sekunden-Buckets geliefert.
# Für längere Zeiträume wird automatisch auf ein sinnvolles Intervall aus
# dieser Liste aufgerundet, damit die Datenmenge kontrollierbar bleibt.
ONE_DAY_BUCKET_SECONDS = 10
TARGET_LONG_RANGE_POINTS = 1800
BUCKET_STEPS = (
    10, 30, 60, 120, 300, 600, 900, 1800,
    3600, 7200, 10800, 21600, 43200, 86400,
)


def _round_bucket(seconds: float) -> int:
    requested = max(10, int(math.ceil(seconds)))
    for step in BUCKET_STEPS:
        if step >= requested:
            return step
    return BUCKET_STEPS[-1]


def _adaptive_bucket(duration_seconds: int, name: str) -> int:
    if name in {'today', 'yesterday'} or duration_seconds <= 86400:
        return ONE_DAY_BUCKET_SECONDS
    return _round_bucket(duration_seconds / TARGET_LONG_RANGE_POINTS)


def adaptive_bounds(name: str) -> tuple[int, int, int]:
    now = datetime.now().astimezone()
    if name == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif name == 'yesterday':
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    elif name == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif name == 'last_month':
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (end - timedelta(days=1)).replace(day=1)
    elif name == 'year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        seconds = energy_history.RANGES.get(name, energy_history.RANGES['7d'])[1]
        end = now
        start = end - timedelta(seconds=seconds)

    duration = max(1, int((end - start).total_seconds()))
    bucket = _adaptive_bucket(duration, name)
    return int(start.timestamp()), int(end.timestamp()), bucket


energy_history._bounds = adaptive_bounds

# Die Anzeige muss Sekunden korrekt ausgeben; die ältere Fassung rundete alles
# unter einer Stunde auf Minuten und hätte bei 10 Sekunden "0 min" gezeigt.
page = runtime.PAGE
page = page.replace(
    "function energyResolutionText(seconds){const s=Number(seconds)||0;if(s<3600)return Math.round(s/60)+' min';if(s<86400)return (s/3600).toLocaleString('de-DE',{maximumFractionDigits:1})+' Std';return (s/86400).toLocaleString('de-DE',{maximumFractionDigits:1})+' Tage'}",
    "function energyResolutionText(seconds){const s=Number(seconds)||0;if(s<60)return Math.round(s)+' s';if(s<3600)return Math.round(s/60)+' min';if(s<86400)return (s/3600).toLocaleString('de-DE',{maximumFractionDigits:1})+' Std';return (s/86400).toLocaleString('de-DE',{maximumFractionDigits:1})+' Tage'}",
)
page = page.replace(
    'Rohmesswerte werden ohne Vorverdichtung gespeichert.',
    'Rohmesswerte werden ohne Vorverdichtung gespeichert. Für die Tagesansicht sind 10 Sekunden vorgesehen.',
)

runtime.PAGE = page
legacy.PAGE = page
