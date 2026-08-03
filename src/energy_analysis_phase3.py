#!/usr/bin/env python3
"""Phase 3: Energieprofile und Vergleiche mit dem jeweiligen Vorzeitraum."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from flask import Response, jsonify, request

import energy_chart_phase2 as previous
import energy_history

app = previous.app
legacy = previous.legacy
runtime = previous.runtime

PROFILES = {'day', 'week', 'month', 'year'}


def _periods(profile: str) -> tuple[datetime, datetime, datetime, datetime, str]:
    now = datetime.now().astimezone()
    if profile == 'day':
        current_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_end = now
        previous_end = current_start
        previous_start = previous_end - timedelta(days=1)
        label = 'Heute ↔ Gestern'
    elif profile == 'week':
        current_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        current_end = now
        previous_end = current_start
        previous_start = previous_end - timedelta(days=7)
        label = 'Diese Woche ↔ Vorwoche'
    elif profile == 'month':
        current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_end = now
        previous_end = current_start
        previous_start = (previous_end - timedelta(days=1)).replace(day=1)
        label = 'Dieser Monat ↔ Vormonat'
    else:
        current_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        current_end = now
        previous_start = current_start.replace(year=current_start.year - 1)
        previous_end = now.replace(year=now.year - 1)
        label = 'Dieses Jahr ↔ Vorjahr'
    return current_start, current_end, previous_start, previous_end, label


def _bucket_key(profile: str, timestamp: int, period_start: datetime) -> int:
    dt = datetime.fromtimestamp(timestamp).astimezone()
    if profile == 'day':
        return dt.hour
    if profile == 'week':
        return dt.weekday()
    if profile == 'month':
        return dt.day - 1
    return dt.month - 1


def _labels(profile: str, start: datetime) -> list[str]:
    if profile == 'day':
        return [f'{hour:02d}:00' for hour in range(24)]
    if profile == 'week':
        return ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    if profile == 'month':
        return [str(day) for day in range(1, monthrange(start.year, start.month)[1] + 1)]
    return ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']


def _rows(start: datetime, end: datetime) -> list[dict[str, Any]]:
    with energy_history._connect() as db:
        result = db.execute(
            '''SELECT ts, power_w, energy_kwh FROM measurements
               WHERE ts BETWEEN ? AND ? ORDER BY ts ASC''',
            (int(start.timestamp()), int(end.timestamp())),
        ).fetchall()
    return [dict(row) for row in result]


def _consumption(rows: list[dict[str, Any]]) -> float:
    energy = [float(row['energy_kwh']) for row in rows if row.get('energy_kwh') is not None]
    if len(energy) >= 2:
        delta = energy[-1] - energy[0]
        if delta >= 0:
            return delta
    total = 0.0
    previous: dict[str, Any] | None = None
    for row in rows:
        if previous is not None and previous.get('power_w') is not None and row.get('power_w') is not None:
            seconds = max(0, int(row['ts']) - int(previous['ts']))
            total += (float(previous['power_w']) + float(row['power_w'])) / 2.0 * seconds / 3_600_000.0
        previous = row
    return total


def _series(profile: str, start: datetime, end: datetime) -> dict[str, Any]:
    rows = _rows(start, end)
    labels = _labels(profile, start)
    grouped: list[list[dict[str, Any]]] = [[] for _ in labels]
    for row in rows:
        index = _bucket_key(profile, int(row['ts']), start)
        if 0 <= index < len(grouped):
            grouped[index].append(row)
    values = [round(_consumption(bucket), 4) if bucket else None for bucket in grouped]
    powers = [
        round(sum(float(row['power_w']) for row in bucket if row.get('power_w') is not None) /
              max(1, sum(1 for row in bucket if row.get('power_w') is not None)), 1)
        if any(row.get('power_w') is not None for row in bucket) else None
        for bucket in grouped
    ]
    total = round(_consumption(rows), 4)
    peak = max((float(row['power_w']) for row in rows if row.get('power_w') is not None), default=None)
    average = (
        sum(float(row['power_w']) for row in rows if row.get('power_w') is not None) /
        max(1, sum(1 for row in rows if row.get('power_w') is not None))
    ) if any(row.get('power_w') is not None for row in rows) else None
    return {
        'start': int(start.timestamp()), 'end': int(end.timestamp()), 'labels': labels,
        'consumption_kwh': values, 'average_power_w': powers, 'total_kwh': total,
        'peak_power_w': round(peak, 1) if peak is not None else None,
        'average_total_power_w': round(average, 1) if average is not None else None,
        'samples': len(rows),
    }


@app.get('/_internal/energy/analysis')
@legacy.login_required
def energy_analysis() -> Response:
    profile = str(request.args.get('profile', 'day')).lower()
    if profile not in PROFILES:
        profile = 'day'
    current_start, current_end, previous_start, previous_end, label = _periods(profile)
    current = _series(profile, current_start, current_end)
    previous_period = _series(profile, previous_start, previous_end)
    previous_total = float(previous_period['total_kwh'] or 0.0)
    difference = float(current['total_kwh'] or 0.0) - previous_total
    change = None if previous_total <= 0 else difference / previous_total * 100.0
    settings = energy_history._settings()
    price = float(settings.get('price_eur_kwh', 0.31) or 0.0)
    return jsonify({
        'ok': True, 'profile': profile, 'label': label,
        'current': current, 'previous': previous_period,
        'difference_kwh': round(difference, 4),
        'change_percent': round(change, 1) if change is not None else None,
        'current_cost_eur': round(float(current['total_kwh']) * price, 2),
        'previous_cost_eur': round(previous_total * price, 2),
    })


SECTION = r'''
<div class="section energy-analysis"><div class="toolbar"><div><h2>Erweiterte Energieanalyse</h2><div class="muted">Verbrauchsprofile und direkter Vergleich mit dem jeweiligen Vorzeitraum.</div></div><div class="energy-analysis-controls"><select id="energyAnalysisProfile" onchange="loadEnergyAnalysis()"><option value="day">Tagesprofil</option><option value="week">Wochenprofil</option><option value="month">Monatsprofil</option><option value="year">Jahresprofil</option></select><button class="secondary" onclick="loadEnergyAnalysis()">Aktualisieren</button></div></div><div class="energy-analysis-metrics"><div class="card"><div class="muted">Aktueller Zeitraum</div><div class="value" id="analysisCurrent">—</div></div><div class="card"><div class="muted">Vorzeitraum</div><div class="value" id="analysisPrevious">—</div></div><div class="card"><div class="muted">Veränderung</div><div class="value" id="analysisChange">—</div></div><div class="card"><div class="muted">Kosten aktuell</div><div class="value" id="analysisCost">—</div></div><div class="card"><div class="muted">Lastspitze</div><div class="value" id="analysisPeak">—</div></div><div class="card"><div class="muted">Messpunkte</div><div class="value" id="analysisSamples">—</div></div></div><div class="analysis-legend"><span><i class="analysis-current"></i>Aktueller Zeitraum</span><span><i class="analysis-previous"></i>Vorzeitraum</span></div><svg id="energyAnalysisChart" viewBox="0 0 1400 390" preserveAspectRatio="none" role="img" aria-label="Vergleich der Energieprofile"></svg><div id="energyAnalysisInfo" class="muted"></div></div>
'''

STYLE = r'''
.energy-analysis{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;margin-top:20px}.energy-analysis-controls{display:flex;gap:8px;flex-wrap:wrap}.energy-analysis-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:16px 0}.energy-analysis-metrics .card{padding:14px}.analysis-legend{display:flex;gap:18px;align-items:center;margin:8px 0 4px;font-size:.88rem;color:var(--muted)}.analysis-legend span{display:flex;align-items:center;gap:6px}.analysis-legend i{display:inline-block;width:12px;height:12px;border-radius:3px}.analysis-current{background:var(--accent)}.analysis-previous{background:var(--muted);opacity:.48}#energyAnalysisChart{width:100%;height:390px;display:block}.analysis-grid{stroke:var(--line);stroke-width:1}.analysis-axis{fill:var(--muted);font-size:12px}.analysis-bar-current{fill:var(--accent)}.analysis-bar-previous{fill:var(--muted);opacity:.42}@media(max-width:1000px){.energy-analysis-metrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:650px){.energy-analysis-metrics{grid-template-columns:repeat(2,1fr)}#energyAnalysisChart{height:300px}}
'''

JS = r'''
let energyAnalysisData=null;
function renderEnergyAnalysis(){const d=energyAnalysisData;if(!d)return;const svg=$('energyAnalysisChart'),cur=d.current||{},prev=d.previous||{},labels=cur.labels||[],a=cur.consumption_kwh||[],b=prev.consumption_kwh||[];const W=1400,H=390,L=66,R=20,T=24,B=56,max=Math.max(.001,...a.map(v=>Number(v)||0),...b.map(v=>Number(v)||0));let out='';for(let i=0;i<=4;i++){const y=T+i*(H-T-B)/4,val=max*(1-i/4);out+=`<line class="analysis-grid" x1="${L}" y1="${y}" x2="${W-R}" y2="${y}"/><text class="analysis-axis" x="${L-8}" y="${y+4}" text-anchor="end">${energyFmt(val,3)} kWh</text>`}const slot=(W-L-R)/Math.max(1,labels.length),bw=Math.max(3,Math.min(28,slot*.34)),y=v=>T+(1-(Number(v)||0)/max)*(H-T-B);labels.forEach((label,i)=>{const cx=L+slot*(i+.5),pv=Number(b[i])||0,cv=Number(a[i])||0;out+=`<rect class="analysis-bar-previous" x="${cx-bw-1}" y="${y(pv)}" width="${bw}" height="${H-B-y(pv)}"><title>${label} · Vorzeitraum: ${energyFmt(pv,4)} kWh</title></rect><rect class="analysis-bar-current" x="${cx+1}" y="${y(cv)}" width="${bw}" height="${H-B-y(cv)}"><title>${label} · Aktuell: ${energyFmt(cv,4)} kWh</title></rect>`;const step=Math.max(1,Math.ceil(labels.length/12));if(i%step===0||i===labels.length-1)out+=`<text class="analysis-axis" x="${cx}" y="${H-18}" text-anchor="middle">${label}</text>`});svg.innerHTML=out}
async function loadEnergyAnalysis(){try{const profile=$('energyAnalysisProfile')?.value||'day',d=await api('/_internal/energy/analysis?profile='+encodeURIComponent(profile));energyAnalysisData=d;const c=d.current||{},p=d.previous||{};$('analysisCurrent').textContent=energyFmt(c.total_kwh,3)+' kWh';$('analysisPrevious').textContent=energyFmt(p.total_kwh,3)+' kWh';$('analysisChange').textContent=d.change_percent===null?'Keine Basis':(d.change_percent>0?'+':'')+energyFmt(d.change_percent,1)+' %';$('analysisCost').textContent=energyFmt(d.current_cost_eur,2)+' €';$('analysisPeak').textContent=energyFmt(c.peak_power_w)+' W';$('analysisSamples').textContent=String(c.samples||0);$('energyAnalysisInfo').textContent=d.label+' · '+new Date(c.start*1000).toLocaleString('de-DE')+' bis '+new Date(c.end*1000).toLocaleString('de-DE')+' · Differenz '+(d.difference_kwh>0?'+':'')+energyFmt(d.difference_kwh,3)+' kWh';renderEnergyAnalysis()}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
marker = '<div class="section energy-professional">'
page = page.replace(marker, SECTION + marker, 1)
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'loadEnergyAnalysis();refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
