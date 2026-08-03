#!/usr/bin/env python3
"""Konfiguration und Status der hochauflösenden Energieerfassung."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import energy_history

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime
STATE_FILE = Path('/var/lib/powergateway/energy_collector_state.json')
ALLOWED_INTERVALS = (5, 10, 30, 60)
DEFAULT_INTERVAL = 10


def _state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


@app.get('/_internal/energy/collection')
@legacy.login_required
def energy_collection_get() -> Response:
    settings = energy_history._settings()
    try:
        interval = int(settings.get('sample_interval_seconds', DEFAULT_INTERVAL))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL
    if interval not in ALLOWED_INTERVALS:
        interval = DEFAULT_INTERVAL
    return jsonify({
        'ok': True,
        'sample_interval_seconds': interval,
        'allowed_intervals': list(ALLOWED_INTERVALS),
        'raw_storage': True,
        'state': _state(),
    })


@app.post('/_internal/energy/collection')
@legacy.login_required
def energy_collection_save() -> Response:
    data = request.get_json(silent=True) or {}
    try:
        interval = int(data.get('sample_interval_seconds', DEFAULT_INTERVAL))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Ungültiges Erfassungsintervall.'}), 400
    if interval not in ALLOWED_INTERVALS:
        return jsonify({'ok': False, 'error': 'Erlaubt sind 5, 10, 30 oder 60 Sekunden.'}), 400

    settings = energy_history._settings()
    settings['sample_interval_seconds'] = interval
    energy_history._write_settings(settings)
    return jsonify({
        'ok': True,
        'sample_interval_seconds': interval,
        'message': f'Messwerterfassung auf {interval} Sekunden eingestellt.',
    })


STYLE = r'''
.energy-collection{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-top:14px}.energy-collection label{min-width:220px}.energy-collection-status{margin-top:8px}
'''

HTML = r'''
<div class="energy-collection"><label>Messwerterfassung<select id="energySampleInterval"><option value="5">Alle 5 Sekunden</option><option value="10" selected>Alle 10 Sekunden</option><option value="30">Alle 30 Sekunden</option><option value="60">Alle 60 Sekunden</option></select></label><button class="secondary" onclick="saveEnergyCollectionSettings()">Erfassung speichern</button></div><div id="energyCollectionStatus" class="muted energy-collection-status">Rohmesswerte werden ohne Vorverdichtung gespeichert. Tagesansicht: 10 Sekunden.</div>
'''

JS = r'''
async function loadEnergyCollectionSettings(){try{const d=await api('/_internal/energy/collection');$('energySampleInterval').value=String(d.sample_interval_seconds||10);const s=d.state||{},last=s.last_result||{};$('energyCollectionStatus').textContent='Rohdatenspeicherung aktiv · Intervall '+(d.sample_interval_seconds||10)+' s'+(last.timestamp?' · letzte Speicherung '+new Date(last.timestamp*1000).toLocaleString('de-DE'):'')}catch(e){$('energyCollectionStatus').textContent=e.message}}
async function saveEnergyCollectionSettings(){try{const d=await api('/_internal/energy/collection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sample_interval_seconds:Number($('energySampleInterval').value)})});notice(d.message,true);await loadEnergyCollectionSettings()}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<div class="muted energy-reset-note">', HTML + '<div class="muted energy-reset-note">', 1)
page = page.replace('async function loadEnergyHistory(){', JS + 'async function loadEnergyHistory(){', 1)
page = page.replace('loadEnergyHistory();setInterval(loadEnergyHistory,30000);', 'loadEnergyHistory();loadEnergyCollectionSettings();setInterval(loadEnergyHistory,30000);setInterval(loadEnergyCollectionSettings,30000);', 1)
runtime.PAGE = page
legacy.PAGE = page
