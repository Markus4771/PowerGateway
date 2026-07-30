#!/usr/bin/env python3
"""Dauerhafte Anzeige des heutigen Gesamtverbrauchs in der Energiegraphik."""
from __future__ import annotations

from flask import Response, jsonify

import webapp_features as features
import energy_history as energy

app = features.app
legacy = features.legacy
runtime = features.runtime


@app.get('/_internal/energy/daily-total')
@legacy.login_required
def energy_daily_total() -> Response:
    data = energy.history('today')
    summary = data.get('summary', {})
    return jsonify({
        'ok': True,
        'date': data.get('start'),
        'consumption_kwh': summary.get('consumption_kwh', 0.0),
        'energy_cost_eur': summary.get('energy_cost_eur', 0.0),
        'samples': summary.get('samples', 0),
    })


STYLE = r'''
.energy-daily-total{border-color:var(--accent)!important;background:color-mix(in srgb,var(--accent) 8%,var(--surface))}.energy-daily-total .value{font-size:1.65rem}.energy-daily-caption{margin-top:4px;font-size:.82rem;color:var(--muted)}
'''

CARD = r'''<div class="card energy-daily-total"><div class="muted">Tagesverbrauch gesamt</div><div class="value" id="energyDailyTotal">—</div><div class="energy-daily-caption" id="energyDailyCost">Heute seit 00:00 Uhr</div></div>'''

JS = r'''
async function loadEnergyDailyTotal(){try{const d=await api('/_internal/energy/daily-total');$('energyDailyTotal').textContent=energyFmt(d.consumption_kwh,3)+' kWh';$('energyDailyCost').textContent='Heute seit 00:00 Uhr · '+energyFmt(d.energy_cost_eur,2)+' €'}catch(e){$('energyDailyTotal').textContent='—';$('energyDailyCost').textContent=e.message}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<div class="energy-metrics">', '<div class="energy-metrics">' + CARD, 1)
page = page.replace('async function loadEnergyHistory(){', JS + 'async function loadEnergyHistory(){', 1)
page = page.replace('renderEnergyChart()}catch(e){notice(e.message,false)}}', 'renderEnergyChart();await loadEnergyDailyTotal()}catch(e){notice(e.message,false)}}', 1)
page = page.replace('loadEnergyHistory();setInterval(loadEnergyHistory,30000);', 'loadEnergyHistory();loadEnergyDailyTotal();setInterval(loadEnergyHistory,30000);setInterval(loadEnergyDailyTotal,30000);', 1)
runtime.PAGE = page
legacy.PAGE = page
