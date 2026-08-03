#!/usr/bin/env python3
"""Phase 4: adaptive serverseitige Verdichtung für Energiezeitreihen."""
from __future__ import annotations

import math
from typing import Any

from flask import Response, jsonify, request

import energy_analysis_phase3 as previous
import energy_history

app = previous.app
legacy = previous.legacy
runtime = previous.runtime

MIN_POINTS = 300
DEFAULT_POINTS = 1400
MAX_POINTS = 2000
NICE_BUCKETS = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600,
                7200, 14400, 21600, 43200, 86400, 172800, 604800)


def _nice_bucket(duration: int, max_points: int) -> int:
    """Wählt das kleinste gut lesbare Intervall unterhalb der Punktgrenze."""
    required = max(1, math.ceil(duration / max(1, max_points)))
    try:
        sample_interval = int(energy_history._settings().get('sample_interval_seconds', 30))
    except (TypeError, ValueError):
        sample_interval = 30
    required = max(required, sample_interval)
    for bucket in NICE_BUCKETS:
        if bucket >= required:
            return bucket
    return NICE_BUCKETS[-1]


def adaptive_history(start: int, end: int, max_points: int) -> dict[str, Any]:
    duration = max(1, end - start)
    bucket = _nice_bucket(duration, max_points)
    with energy_history._connect() as db:
        rows = db.execute(
            '''SELECT (ts / ?) * ? bucket,
                      AVG(power_w) power_w,
                      MIN(power_w) power_min_w,
                      MAX(power_w) power_max_w,
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
    points = []
    raw_samples = 0
    for row in rows:
        raw_samples += int(row['samples'] or 0)
        points.append({
            'ts': int(row['bucket']),
            'power_w': row['power_w'],
            'power_min_w': row['power_min_w'],
            'power_max_w': row['power_max_w'],
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
        })
    return {
        'ok': True,
        'start': start,
        'end': end,
        'duration_seconds': duration,
        'bucket_seconds': bucket,
        'point_count': len(points),
        'raw_sample_count': raw_samples,
        'max_points': max_points,
        'adaptive': True,
        'points': points,
    }


@app.get('/_internal/energy/adaptive-history')
@legacy.login_required
def energy_adaptive_history() -> Response:
    try:
        start = int(request.args.get('start', '0'))
        end = int(request.args.get('end', '0'))
        max_points = int(request.args.get('max_points', str(DEFAULT_POINTS)))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Ungültige Zeit- oder Punktangabe.'}), 400
    max_points = max(MIN_POINTS, min(MAX_POINTS, max_points))
    if start <= 0 or end <= start:
        return jsonify({'ok': False, 'error': 'Der angeforderte Zeitraum ist ungültig.'}), 400
    # Schutz vor versehentlich extrem großen Abfragen.
    if end - start > 10 * 365 * 86400:
        return jsonify({'ok': False, 'error': 'Der Zeitraum darf höchstens zehn Jahre umfassen.'}), 400
    return jsonify(adaptive_history(start, end, max_points))


STYLE = r'''
.energy-adaptive-status{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;background:#eef3f6;font-size:.78rem}.energy-adaptive-status.loading{opacity:.65}.energy-peak-line{stroke:#bd2c2455;stroke-width:1;vector-effect:non-scaling-stroke}
'''

SCRIPT = r'''
let energyFullStart=null,energyFullEnd=null,energyAdaptiveTimer=null,energyAdaptiveRequest=0;
function energyAdaptiveLimit(){const svg=$('energyChart');const width=svg?svg.getBoundingClientRect().width:1200;return Math.max(300,Math.min(2000,Math.round(width*1.35)))}
function energyAdaptiveText(seconds){const s=Number(seconds)||0;if(s<60)return s+' s';if(s<3600)return Math.round(s/60)+' min';if(s<86400)return (s/3600).toLocaleString('de-DE',{maximumFractionDigits:1})+' Std';return (s/86400).toLocaleString('de-DE',{maximumFractionDigits:1})+' Tage'}
function energyAdaptiveStatus(text,loading=false){const el=$('energyAdaptiveStatus');if(!el)return;el.textContent=text;el.classList.toggle('loading',loading)}
async function energyFetchAdaptive(start,end){if(!energyData||!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return;const requestId=++energyAdaptiveRequest;energyAdaptiveStatus('Details werden geladen …',true);try{const maxPoints=energyAdaptiveLimit();const d=await api('/_internal/energy/adaptive-history?start='+Math.floor(start)+'&end='+Math.ceil(end)+'&max_points='+maxPoints);if(requestId!==energyAdaptiveRequest)return;energyData.points=d.points||[];energyData.bucket_seconds=d.bucket_seconds;energyData.adaptive_meta=d;energyViewStart=d.start;energyViewEnd=d.end;renderEnergyChart();energyAdaptiveStatus((d.point_count||0).toLocaleString('de-DE')+' Punkte · '+energyAdaptiveText(d.bucket_seconds)+' · '+(d.raw_sample_count||0).toLocaleString('de-DE')+' Rohwerte')}catch(e){if(requestId===energyAdaptiveRequest)energyAdaptiveStatus('Adaptive Abfrage fehlgeschlagen')}}
function energyScheduleAdaptive(start=null,end=null,delay=180){clearTimeout(energyAdaptiveTimer);const s=start??energyViewStart,e=end??energyViewEnd;if(!Number.isFinite(s)||!Number.isFinite(e))return;energyAdaptiveTimer=setTimeout(()=>energyFetchAdaptive(s,e),delay)}
const energyPhase4OriginalLoad=loadEnergyHistory;
loadEnergyHistory=async function(){await energyPhase4OriginalLoad();if(!energyData)return;energyFullStart=Number(energyData.requested_start||energyData.start);energyFullEnd=Number(energyData.end);const pts=energyData.points||[];if(pts.length){energyViewStart=energyFullStart;energyViewEnd=energyFullEnd;energyScheduleAdaptive(energyFullStart,energyFullEnd,0)}};
const energyPhase4OriginalZoom=energyZoomBy;
energyZoomBy=function(factor,center=null){if(!energyData)return;const fullStart=energyFullStart??energyData.start,fullEnd=energyFullEnd??energyData.end;const start=energyViewStart??fullStart,end=energyViewEnd??fullEnd,mid=center??((start+end)/2);let span=Math.max(30,(end-start)*factor);span=Math.min(fullEnd-fullStart,span);let ns=mid-span/2,ne=mid+span/2;if(ns<fullStart){ne+=fullStart-ns;ns=fullStart}if(ne>fullEnd){ns-=ne-fullEnd;ne=fullEnd}energyViewStart=Math.max(fullStart,ns);energyViewEnd=Math.min(fullEnd,ne);energyScheduleAdaptive(energyViewStart,energyViewEnd);};
energyResetZoom=function(){if(!energyData)return;energyViewStart=energyFullStart??energyData.start;energyViewEnd=energyFullEnd??energyData.end;energyScheduleAdaptive(energyViewStart,energyViewEnd,0)};
window.addEventListener('resize',()=>{if(energyViewStart&&energyViewEnd)energyScheduleAdaptive(energyViewStart,energyViewEnd,350)});
'''

page = energy_history.runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace(
    '<span class="muted energy-zoom-status" id="energyZoomStatus">Gesamter Zeitraum</span>',
    '<span class="muted energy-zoom-status" id="energyZoomStatus">Gesamter Zeitraum</span><span id="energyAdaptiveStatus" class="energy-adaptive-status">Adaptive Auflösung</span>',
    1,
)
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)

energy_history.runtime.PAGE = page
energy_history.legacy.PAGE = page
