#!/usr/bin/env python3
"""Feinere Daten- und Darstellungsauflösung der Energiegraphik ab 1.3.12-dev."""
from __future__ import annotations

from datetime import datetime, timedelta

import energy_history

# Die Messwerte werden weiterhin minütlich erfasst. Für die Darstellung werden
# deutlich kleinere Zeitfenster verwendet, ohne die SQLite-Rohdaten zu ändern.
REFINED_RANGES = {
    'today': ('Heute', 24 * 3600, 60),
    'yesterday': ('Gestern', 24 * 3600, 60),
    '7d': ('7 Tage', 7 * 86400, 15 * 60),
    '30d': ('30 Tage', 30 * 86400, 3600),
    'month': ('Dieser Monat', 32 * 86400, 3600),
    'last_month': ('Letzter Monat', 32 * 86400, 3600),
    'year': ('Dieses Jahr', 370 * 86400, 6 * 3600),
}

energy_history.RANGES.clear()
energy_history.RANGES.update(REFINED_RANGES)


def refined_bounds(name: str) -> tuple[int, int, int]:
    """Berechnet Kalendergrenzen mit den feineren Diagramm-Intervallen."""
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
        seconds = REFINED_RANGES.get(name, REFINED_RANGES['7d'])[1]
        end = now
        start = end - timedelta(seconds=seconds)
    bucket = REFINED_RANGES.get(name, REFINED_RANGES['7d'])[2]
    return int(start.timestamp()), int(end.timestamp()), bucket


energy_history._bounds = refined_bounds

# Größere interne SVG-Zeichenfläche, mehr Achsenbeschriftungen und mehr sichtbare
# Messpunkte. Die Grafik bleibt durch width:100% weiterhin responsiv.
page = energy_history.runtime.PAGE
page = page.replace(
    'viewBox="0 0 1000 330" preserveAspectRatio="none"',
    'viewBox="0 0 1400 420" preserveAspectRatio="none"',
)
page = page.replace(
    '#energyChart{width:100%;height:330px;',
    '#energyChart{width:100%;height:390px;',
)
page = page.replace(
    '@media(max-width:800px){.energy-metrics{grid-template-columns:repeat(2,1fr)}#energyChart{height:260px}',
    '@media(max-width:800px){.energy-metrics{grid-template-columns:repeat(2,1fr)}#energyChart{height:300px}',
)
page = page.replace(
    'const W=1000,H=330,L=58,R=18,T=20,B=44',
    'const W=1400,H=420,L=70,R=24,T=24,B=52',
)
page = page.replace('for(let i=0;i<5;i++){', 'for(let i=0;i<7;i++){')
page = page.replace(
    'Math.round(i*(pts.length-1)/4)',
    'Math.round(i*(pts.length-1)/6)',
)
page = page.replace(
    'Math.floor(pts.length/40)',
    'Math.floor(pts.length/120)',
)
page = page.replace(
    "$('energyPeriod').textContent=new Date(d.start*1000).toLocaleString('de-DE')+' – '+new Date(d.end*1000).toLocaleString('de-DE');",
    "$('energyPeriod').textContent=new Date(d.start*1000).toLocaleString('de-DE')+' – '+new Date(d.end*1000).toLocaleString('de-DE')+' · Auflösung '+energyResolutionText(d.bucket_seconds);",
)
page = page.replace(
    'function energyFmt(v,d=1){',
    "function energyResolutionText(seconds){const s=Number(seconds)||0;if(s<3600)return Math.round(s/60)+' min';if(s<86400)return (s/3600).toLocaleString('de-DE',{maximumFractionDigits:1})+' Std';return (s/86400).toLocaleString('de-DE',{maximumFractionDigits:1})+' Tage'}\nfunction energyFmt(v,d=1){",
)

energy_history.runtime.PAGE = page
energy_history.legacy.PAGE = page
