#!/usr/bin/env python3
"""Erweiterte Energieauswertung für PowerGateway 1.3.3-dev."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Response, jsonify, request

import webapp_features as features
import energy_history as base

app = features.app
legacy = features.legacy
runtime = features.runtime
DB_FILE = Path('/var/lib/powergateway/energy_history.sqlite3')


def _statistics(start: int, end: int) -> dict:
    if not DB_FILE.exists():
        return {'min_power_w': None, 'max_power_w': None, 'avg_power_w': None,
                'avg_voltage_v': None, 'avg_current_a': None, 'measurement_count': 0}
    with sqlite3.connect(DB_FILE, timeout=20) as db:
        row = db.execute('''SELECT MIN(power_w), MAX(power_w), AVG(power_w),
            AVG(voltage_v), AVG(current_a), COUNT(*)
            FROM measurements WHERE ts BETWEEN ? AND ?''', (start, end)).fetchone()
    return {
        'min_power_w': row[0], 'max_power_w': row[1], 'avg_power_w': row[2],
        'avg_voltage_v': row[3], 'avg_current_a': row[4],
        'measurement_count': int(row[5] or 0),
    }


@app.get('/_internal/energy/statistics')
@legacy.login_required
def energy_statistics() -> Response:
    name = request.args.get('range', 'today')
    if name not in base.RANGES:
        name = 'today'
    start, end, _ = base._bounds(name)
    reset_ts = int(base._settings().get('meter_reset_ts', 0) or 0)
    start = max(start, reset_ts)
    result = _statistics(start, end)
    result.update({'ok': True, 'range': name, 'start': start, 'end': end})
    return jsonify(result)


SECTION = r'''
<div class="section energy-professional">
  <div class="toolbar"><div><h2>Energiestatistik</h2><div class="muted">Minimal-, Maximal- und Durchschnittswerte für den gewählten Zeitraum.</div></div></div>
  <div class="energy-pro-grid">
    <div class="card"><div class="muted">Minimale Leistung</div><div class="value" id="energyMinPower">—</div></div>
    <div class="card"><div class="muted">Maximale Leistung</div><div class="value" id="energyMaxPower">—</div></div>
    <div class="card"><div class="muted">Durchschnittsleistung</div><div class="value" id="energyAvgPower">—</div></div>
    <div class="card"><div class="muted">Ø Spannung</div><div class="value" id="energyAvgVoltage">—</div></div>
    <div class="card"><div class="muted">Ø Stromstärke</div><div class="value" id="energyAvgCurrent">—</div></div>
    <div class="card"><div class="muted">Messungen im Zeitraum</div><div class="value" id="energyMeasurementCount">—</div></div>
  </div>
</div>
'''

STYLE = r'''
.energy-professional{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;margin-top:20px}.energy-pro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.energy-pro-grid .card{padding:14px}@media(max-width:800px){.energy-pro-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:480px){.energy-pro-grid{grid-template-columns:1fr}}
'''

JS = r'''
async function loadEnergyStatistics(){try{const range=$('energyRange')?.value||'today';const d=await api('/_internal/energy/statistics?range='+encodeURIComponent(range));$('energyMinPower').textContent=energyFmt(d.min_power_w)+' W';$('energyMaxPower').textContent=energyFmt(d.max_power_w)+' W';$('energyAvgPower').textContent=energyFmt(d.avg_power_w)+' W';$('energyAvgVoltage').textContent=energyFmt(d.avg_voltage_v)+' V';$('energyAvgCurrent').textContent=energyFmt(d.avg_current_a,2)+' A';$('energyMeasurementCount').textContent=String(d.measurement_count||0)}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('</section>', SECTION + '</section>', 1)
page = page.replace('async function loadEnergyHistory(){', 'async function loadEnergyHistory(){')
page = page.replace("renderEnergyChart()}catch(e){notice(e.message,false)}}", "renderEnergyChart();await loadEnergyStatistics()}catch(e){notice(e.message,false)}}")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'loadEnergyStatistics();refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
