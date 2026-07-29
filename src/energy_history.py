#!/usr/bin/env python3
"""Persistente Stromverbrauchshistorie und Dashboard-API für PowerGateway."""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import webapp_features as features

app = features.app
legacy = features.legacy
runtime = features.runtime
DATA_DIR = Path('/var/lib/powergateway')
STATUS_FILE = DATA_DIR / 'status.json'
DB_FILE = DATA_DIR / 'energy_history.sqlite3'
SETTINGS_FILE = DATA_DIR / 'energy_settings.json'

RANGES = {
    'today': ('Heute', 24 * 3600, 10 * 60),
    'yesterday': ('Gestern', 24 * 3600, 10 * 60),
    '7d': ('7 Tage', 7 * 86400, 3600),
    '30d': ('30 Tage', 30 * 86400, 4 * 3600),
    'month': ('Dieser Monat', 32 * 86400, 4 * 3600),
    'last_month': ('Letzter Monat', 32 * 86400, 4 * 3600),
    'year': ('Dieses Jahr', 370 * 86400, 86400),
}
POWER_KEYS = ('power_w', 'power', 'watt', 'leistung', 'active_power', '1-0:16.7.0')
ENERGY_KEYS = ('energy_kwh', 'total_kwh', 'energy_total', 'verbrauch_kwh', '1-0:1.8.0')
VOLTAGE_KEYS = ('voltage_v', 'voltage', 'spannung')
CURRENT_KEYS = ('current_a', 'current', 'strom')
FREQUENCY_KEYS = ('frequency_hz', 'frequency', 'frequenz')
FACTOR_KEYS = ('power_factor', 'cos_phi', 'leistungsfaktor')


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_FILE, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=NORMAL')
    db.execute('''CREATE TABLE IF NOT EXISTS measurements (
        ts INTEGER PRIMARY KEY,
        power_w REAL,
        energy_kwh REAL,
        voltage_v REAL,
        current_a REAL,
        frequency_hz REAL,
        power_factor REAL
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(ts)')
    return db


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_settings(settings: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(SETTINGS_FILE)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ('value', 'wert', 'reading'):
            if key in value:
                return _number(value[key])
        return None
    text = str(value).strip().replace(',', '.')
    filtered = ''.join(ch for ch in text if ch.isdigit() or ch in '.-')
    try:
        return float(filtered) if filtered not in {'', '-', '.', '-.'} else None
    except ValueError:
        return None


def _find(data: Any, keys: tuple[str, ...]) -> float | None:
    wanted = {key.lower() for key in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in wanted:
                found = _number(value)
                if found is not None:
                    return found
        for value in data.values():
            found = _find(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find(value, keys)
            if found is not None:
                return found
    return None


def extract_measurement(status: dict[str, Any]) -> dict[str, float | None]:
    source = status.get('last_measurement') or status.get('measurement') or status.get('measurements') or status
    return {
        'power_w': _find(source, POWER_KEYS),
        'energy_kwh': _find(source, ENERGY_KEYS),
        'voltage_v': _find(source, VOLTAGE_KEYS),
        'current_a': _find(source, CURRENT_KEYS),
        'frequency_hz': _find(source, FREQUENCY_KEYS),
        'power_factor': _find(source, FACTOR_KEYS),
    }


def sample() -> dict[str, Any]:
    status = _read_json(STATUS_FILE)
    values = extract_measurement(status)
    if not any(value is not None for value in values.values()):
        return {'ok': False, 'message': 'Noch keine auswertbaren Zählerwerte vorhanden.'}
    ts = int(time.time())
    with _connect() as db:
        db.execute('''INSERT OR REPLACE INTO measurements
            (ts,power_w,energy_kwh,voltage_v,current_a,frequency_hz,power_factor)
            VALUES (?,?,?,?,?,?,?)''', (ts, values['power_w'], values['energy_kwh'], values['voltage_v'], values['current_a'], values['frequency_hz'], values['power_factor']))
    return {'ok': True, 'timestamp': ts, **values}


def _bounds(name: str) -> tuple[int, int, int]:
    now = datetime.now().astimezone()
    if name == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        bucket = 10 * 60
    elif name == 'yesterday':
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        bucket = 10 * 60
    elif name == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        bucket = 4 * 3600
    elif name == 'last_month':
        end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (end - timedelta(days=1)).replace(day=1)
        bucket = 4 * 3600
    elif name == 'year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        bucket = 86400
    else:
        seconds = RANGES.get(name, RANGES['7d'])[1]
        bucket = RANGES.get(name, RANGES['7d'])[2]
        end = now
        start = end - timedelta(seconds=seconds)
    return int(start.timestamp()), int(end.timestamp()), bucket


def _settings() -> dict[str, Any]:
    result = {'price_eur_kwh': 0.31, 'default_range': '7d', 'meter_reset_ts': 0}
    result.update(_read_json(SETTINGS_FILE))
    return result


def history(name: str) -> dict[str, Any]:
    start, end, bucket = _bounds(name)
    settings = _settings()
    reset_ts = max(0, int(settings.get('meter_reset_ts', 0) or 0))
    effective_start = max(start, reset_ts)
    with _connect() as db:
        rows = db.execute('''SELECT (ts / ?) * ? bucket,
            AVG(power_w) power_w, MIN(energy_kwh) energy_min, MAX(energy_kwh) energy_max,
            AVG(voltage_v) voltage_v, AVG(current_a) current_a
            FROM measurements WHERE ts BETWEEN ? AND ?
            GROUP BY bucket ORDER BY bucket''', (bucket, bucket, effective_start, end)).fetchall()
        first_last = db.execute('''SELECT
            (SELECT energy_kwh FROM measurements WHERE ts BETWEEN ? AND ? AND energy_kwh IS NOT NULL ORDER BY ts ASC LIMIT 1) first_energy,
            (SELECT energy_kwh FROM measurements WHERE ts BETWEEN ? AND ? AND energy_kwh IS NOT NULL ORDER BY ts DESC LIMIT 1) last_energy,
            (SELECT power_w FROM measurements WHERE ts BETWEEN ? AND ? AND power_w IS NOT NULL ORDER BY ts DESC LIMIT 1) current_power''', (effective_start, end, effective_start, end, effective_start, end)).fetchone()
    points = []
    estimated_kwh = 0.0
    previous_ts = None
    previous_power = None
    for row in rows:
        ts = int(row['bucket'])
        power = row['power_w']
        if previous_ts is not None and previous_power is not None and power is not None:
            estimated_kwh += ((previous_power + power) / 2.0) * (ts - previous_ts) / 3_600_000.0
        previous_ts, previous_power = ts, power
        points.append({'ts': ts, 'power_w': power, 'energy_kwh': (row['energy_max'] - row['energy_min']) if row['energy_min'] is not None and row['energy_max'] is not None else None, 'voltage_v': row['voltage_v'], 'current_a': row['current_a']})
    meter_kwh = None
    if first_last and first_last['first_energy'] is not None and first_last['last_energy'] is not None:
        meter_kwh = max(0.0, float(first_last['last_energy']) - float(first_last['first_energy']))
    consumption = meter_kwh if meter_kwh is not None else estimated_kwh
    price = float(settings.get('price_eur_kwh', 0.31) or 0)
    return {'ok': True, 'range': name, 'start': effective_start, 'requested_start': start, 'end': end, 'bucket_seconds': bucket, 'points': points, 'summary': {'current_power_w': first_last['current_power'] if first_last else None, 'consumption_kwh': round(consumption, 3), 'cost_eur': round(consumption * price, 2), 'samples': len(points)}, 'settings': settings}


@app.get('/_internal/energy/history')
@legacy.login_required
def energy_history() -> Response:
    name = request.args.get('range', _settings().get('default_range', '7d'))
    if name not in RANGES:
        name = '7d'
    sample()
    return jsonify(history(name))


@app.get('/_internal/energy/settings')
@legacy.login_required
def energy_settings_get() -> Response:
    return jsonify({'ok': True, 'settings': _settings()})


@app.post('/_internal/energy/settings')
@legacy.login_required
def energy_settings_save() -> Response:
    data = request.get_json(silent=True) or {}
    try:
        price = max(0.0, min(10.0, float(data.get('price_eur_kwh', 0.31))))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Ungültiger Strompreis.'}), 400
    default_range = str(data.get('default_range', '7d'))
    if default_range not in RANGES:
        default_range = '7d'
    settings = _settings()
    settings.update({'price_eur_kwh': price, 'default_range': default_range})
    _write_settings(settings)
    return jsonify({'ok': True, 'settings': settings})


@app.post('/_internal/energy/reset-meter-reading')
@legacy.login_required
def energy_reset_meter_reading() -> Response:
    data = request.get_json(silent=True) or {}
    if data.get('confirmation') != 'ZÄHLERSTAND ZURÜCKSETZEN':
        return jsonify({'ok': False, 'error': 'Bestätigung fehlt oder ist ungültig.'}), 400
    now = int(time.time())
    settings = _settings()
    settings['meter_reset_ts'] = now
    _write_settings(settings)
    return jsonify({
        'ok': True,
        'reset_timestamp': now,
        'message': 'Der Berechnungs-Zählerstand wurde zurückgesetzt. Messhistorie und alle Einstellungen bleiben erhalten.',
    })


SECTION = r'''
<div class="section energy-panel"><div class="toolbar"><div><h2>Stromverbrauch</h2><div class="muted">Historische Leistung und Verbrauch. Standardmäßig werden die letzten 7 Tage angezeigt.</div></div><div class="energy-controls"><select id="energyRange" onchange="loadEnergyHistory()"><option value="today">Heute</option><option value="yesterday">Gestern</option><option value="7d" selected>7 Tage</option><option value="30d">30 Tage</option><option value="month">Dieser Monat</option><option value="last_month">Letzter Monat</option><option value="year">Dieses Jahr</option></select><select id="energyChartType" onchange="renderEnergyChart()"><option value="line">Linie</option><option value="bar">Balken</option></select><button class="secondary" onclick="loadEnergyHistory()">Aktualisieren</button></div></div><div class="energy-metrics"><div class="card"><div class="muted">Aktuelle Leistung</div><div class="value" id="energyPower">—</div></div><div class="card"><div class="muted">Verbrauch seit Zählerstand-Reset</div><div class="value" id="energyConsumption">—</div></div><div class="card"><div class="muted">Geschätzte Kosten</div><div class="value" id="energyCost">—</div></div><div class="card"><div class="muted">Datenpunkte</div><div class="value" id="energySamples">—</div></div></div><div id="energyChartEmpty" class="muted energy-empty">Noch keine historischen Messwerte vorhanden.</div><svg id="energyChart" role="img" aria-label="Stromverbrauch im gewählten Zeitraum" viewBox="0 0 1000 330" preserveAspectRatio="none"></svg><div class="energy-settings"><label>Strompreis in €/kWh <input id="energyPrice" type="number" min="0" max="10" step="0.001"></label><button class="secondary" onclick="saveEnergySettings()">Preis speichern</button><button class="danger" onclick="resetMeterReading()">Zählerstand zurücksetzen</button><span class="muted" id="energyPeriod"></span><span class="muted" id="energyResetInfo"></span></div><div class="muted energy-reset-note">Dabei werden nur der Bezugspunkt und die Verbrauchsberechnung zurückgesetzt. Messhistorie, Zählerauswahl, Netzwerk, MQTT, Home Assistant, WireGuard und alle weiteren Einstellungen bleiben erhalten.</div></div>
'''

STYLE = r'''
.energy-panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:20px}.energy-controls{display:flex;gap:8px;flex-wrap:wrap}.energy-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.energy-metrics .card{padding:14px}.energy-metrics .value{margin-top:6px}.energy-empty{text-align:center;padding:70px 15px}.energy-settings{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-top:12px}.energy-settings label{max-width:220px}.energy-settings input{width:100%}.energy-reset-note{margin-top:10px;font-size:.92rem}#energyChart{width:100%;height:330px;display:none;overflow:visible}.energy-grid{stroke:var(--line);stroke-width:1}.energy-axis{fill:var(--muted);font-size:12px}.energy-line{fill:none;stroke:var(--accent);stroke-width:3;vector-effect:non-scaling-stroke}.energy-area{fill:#1677ff18}.energy-bar{fill:var(--accent);opacity:.75}.energy-dot{fill:var(--accent)}@media(max-width:800px){.energy-metrics{grid-template-columns:repeat(2,1fr)}#energyChart{height:260px}.energy-controls select,.energy-controls button{flex:1}}@media(max-width:480px){.energy-metrics{grid-template-columns:1fr 1fr}.energy-panel{padding:14px}}
'''

JS = r'''
let energyData=null;
function energyFmt(v,d=1){return v===null||v===undefined||Number.isNaN(Number(v))?'—':Number(v).toLocaleString('de-DE',{minimumFractionDigits:d,maximumFractionDigits:d})}
function energyDate(ts,range){const d=new Date(ts*1000);return range==='today'||range==='yesterday'?d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'}):d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:range==='year'?'2-digit':undefined})}
function renderEnergyChart(){if(!energyData)return;const svg=$('energyChart'),empty=$('energyChartEmpty'),pts=(energyData.points||[]).filter(p=>p.power_w!==null);if(!pts.length){svg.style.display='none';empty.style.display='block';return}empty.style.display='none';svg.style.display='block';const W=1000,H=330,L=58,R=18,T=20,B=44,max=Math.max(100,...pts.map(p=>Number(p.power_w)||0));const minTs=pts[0].ts,maxTs=pts[pts.length-1].ts||minTs+1;const x=p=>L+(p.ts-minTs)/Math.max(1,maxTs-minTs)*(W-L-R),y=p=>T+(1-(Number(p.power_w)||0)/max)*(H-T-B);let out='';for(let i=0;i<=4;i++){const yy=T+i*(H-T-B)/4,val=max*(1-i/4);out+=`<line class="energy-grid" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text class="energy-axis" x="${L-8}" y="${yy+4}" text-anchor="end">${Math.round(val)} W</text>`}for(let i=0;i<5;i++){const idx=Math.min(pts.length-1,Math.round(i*(pts.length-1)/4)),xx=x(pts[idx]);out+=`<text class="energy-axis" x="${xx}" y="${H-15}" text-anchor="middle">${energyDate(pts[idx].ts,energyData.range)}</text>`}if($('energyChartType').value==='bar'){const bw=Math.max(2,Math.min(30,(W-L-R)/pts.length*.72));out+=pts.map(p=>`<rect class="energy-bar" x="${x(p)-bw/2}" y="${y(p)}" width="${bw}" height="${H-B-y(p)}"><title>${energyDate(p.ts,energyData.range)}: ${energyFmt(p.power_w)} W</title></rect>`).join('')}else{const path=pts.map((p,i)=>`${i?'L':'M'}${x(p).toFixed(1)},${y(p).toFixed(1)}`).join(' ');out+=`<path class="energy-area" d="${path} L${x(pts[pts.length-1])},${H-B} L${x(pts[0])},${H-B} Z"/><path class="energy-line" d="${path}"/>`;out+=pts.filter((p,i)=>i%Math.max(1,Math.floor(pts.length/40))===0).map(p=>`<circle class="energy-dot" cx="${x(p)}" cy="${y(p)}" r="3"><title>${energyDate(p.ts,energyData.range)}: ${energyFmt(p.power_w)} W</title></circle>`).join('')}svg.innerHTML=out}
async function loadEnergyHistory(){try{const range=$('energyRange').value||'7d';const d=await api('/_internal/energy/history?range='+encodeURIComponent(range));energyData=d;const s=d.summary||{};$('energyPower').textContent=energyFmt(s.current_power_w)+' W';$('energyConsumption').textContent=energyFmt(s.consumption_kwh,3)+' kWh';$('energyCost').textContent=energyFmt(s.cost_eur,2)+' €';$('energySamples').textContent=String(s.samples||0);$('energyPrice').value=(d.settings||{}).price_eur_kwh??0.31;$('energyPeriod').textContent=new Date(d.start*1000).toLocaleString('de-DE')+' – '+new Date(d.end*1000).toLocaleString('de-DE');const reset=(d.settings||{}).meter_reset_ts||0;$('energyResetInfo').textContent=reset?'Letzter Zählerstand-Reset: '+new Date(reset*1000).toLocaleString('de-DE'):'';renderEnergyChart()}catch(e){notice(e.message,false)}}
async function saveEnergySettings(){try{await api('/_internal/energy/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({price_eur_kwh:Number($('energyPrice').value),default_range:'7d'})});notice('Strompreis gespeichert.',true);await loadEnergyHistory()}catch(e){notice(e.message,false)}}
async function resetMeterReading(){const text='Damit wird ausschließlich der Berechnungs-Zählerstand auf 0 gesetzt. Alte Messwerte und sämtliche Einstellungen bleiben erhalten.\n\nZum Fortfahren exakt eingeben:\nZÄHLERSTAND ZURÜCKSETZEN';const confirmation=prompt(text,'');if(confirmation===null)return;try{const d=await api('/_internal/energy/reset-meter-reading',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation})});notice(d.message||'Zählerstand zurückgesetzt.',true);await loadEnergyHistory()}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<section id="dashboard" class="tab active">', '<section id="dashboard" class="tab active">' + SECTION)
page = page.replace('refresh();setInterval(refresh,5000);', JS + "loadEnergyHistory();setInterval(loadEnergyHistory,30000);refresh();setInterval(refresh,5000);")
runtime.PAGE = page
legacy.PAGE = page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', action='store_true')
    args = parser.parse_args()
    if args.sample:
        result = sample()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok') else 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
