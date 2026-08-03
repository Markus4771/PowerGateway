#!/usr/bin/env python3
"""Interaktive Energiegraphik für PowerGateway Phase 2 / 1.4.2-dev.

Die Erweiterung bleibt vollständig lokal und benötigt keine JavaScript-CDNs.
Sie ergänzt Messreihen, Zoom, Verschieben, Cursor-Tooltip und Reset.
"""
from __future__ import annotations

from typing import Any

import energy_history

_original_history = energy_history.history


def enhanced_history(name: str) -> dict[str, Any]:
    """Ergänzt Frequenz und Leistungsfaktor passend zur aktuellen Verdichtung."""
    result = _original_history(name)
    start = int(result.get('start', 0) or 0)
    end = int(result.get('end', 0) or 0)
    bucket = max(1, int(result.get('bucket_seconds', 60) or 60))
    with energy_history._connect() as db:
        rows = db.execute(
            '''SELECT (ts / ?) * ? bucket,
                      AVG(frequency_hz) frequency_hz,
                      AVG(power_factor) power_factor
                 FROM measurements
                WHERE ts BETWEEN ? AND ?
                GROUP BY bucket ORDER BY bucket''',
            (bucket, bucket, start, end),
        ).fetchall()
    extra = {
        int(row['bucket']): {
            'frequency_hz': row['frequency_hz'],
            'power_factor': row['power_factor'],
        }
        for row in rows
    }
    for point in result.get('points', []):
        values = extra.get(int(point.get('ts', 0)), {})
        point.update(values)
    result['available_series'] = [
        {'key': 'power_w', 'label': 'Leistung', 'unit': 'W'},
        {'key': 'voltage_v', 'label': 'Spannung', 'unit': 'V'},
        {'key': 'current_a', 'label': 'Strom', 'unit': 'A'},
        {'key': 'frequency_hz', 'label': 'Frequenz', 'unit': 'Hz'},
        {'key': 'power_factor', 'label': 'Leistungsfaktor', 'unit': ''},
    ]
    return result


energy_history.history = enhanced_history

STYLE = r'''
.energy-series-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0}.energy-series-controls label{display:inline-flex;align-items:center;gap:6px;width:auto;padding:7px 10px;border:1px solid var(--line);border-radius:999px;background:var(--surface);cursor:pointer}.energy-series-controls input{width:auto;margin:0}.energy-chart-help{font-size:.85rem}.energy-chart-shell{position:relative;touch-action:none;user-select:none}.energy-chart-shell.grabbing{cursor:grabbing}.energy-chart-shell:not(.grabbing){cursor:crosshair}.energy-tooltip{position:absolute;display:none;z-index:5;pointer-events:none;min-width:180px;max-width:280px;padding:9px 11px;border-radius:9px;background:#102433ed;color:#fff;box-shadow:0 8px 26px #0003;font-size:.82rem;line-height:1.45}.energy-tooltip strong{display:block;margin-bottom:4px}.energy-crosshair{stroke:var(--muted);stroke-width:1;stroke-dasharray:4 4;vector-effect:non-scaling-stroke}.energy-series-line{fill:none;stroke-width:2.5;vector-effect:non-scaling-stroke}.energy-series-power_w{stroke:var(--accent)}.energy-series-voltage_v{stroke:#14804a}.energy-series-current_a{stroke:#ad6800}.energy-series-frequency_hz{stroke:#7b3fc6}.energy-series-power_factor{stroke:#bd2c24}.energy-legend-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}.energy-chart-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.energy-zoom-status{font-variant-numeric:tabular-nums}@media(max-width:600px){.energy-series-controls label{font-size:.82rem}.energy-chart-actions button{flex:1}}
'''

CONTROLS = r'''
<div class="energy-series-controls" id="energySeriesControls">
  <strong>Messreihen:</strong>
  <label><input type="checkbox" value="power_w" checked onchange="renderEnergyChart()">Leistung</label>
  <label><input type="checkbox" value="voltage_v" onchange="renderEnergyChart()">Spannung</label>
  <label><input type="checkbox" value="current_a" onchange="renderEnergyChart()">Strom</label>
  <label><input type="checkbox" value="frequency_hz" onchange="renderEnergyChart()">Frequenz</label>
  <label><input type="checkbox" value="power_factor" onchange="renderEnergyChart()">Leistungsfaktor</label>
</div>
<div class="energy-chart-actions"><button type="button" class="secondary" onclick="energyZoomBy(0.5)">Hineinzoomen</button><button type="button" class="secondary" onclick="energyZoomBy(2)">Herauszoomen</button><button type="button" class="secondary" onclick="energyResetZoom()">Zoom zurücksetzen</button><span class="muted energy-zoom-status" id="energyZoomStatus">Gesamter Zeitraum</span><span class="muted energy-chart-help">Mausrad: Zoom · Ziehen: Verschieben · Doppelklick: Reset</span></div>
'''

JS = r'''
let energyViewStart=null,energyViewEnd=null,energyDrag=null,energyChartBound=false;
const energySeriesMeta={power_w:{label:'Leistung',unit:'W'},voltage_v:{label:'Spannung',unit:'V'},current_a:{label:'Strom',unit:'A'},frequency_hz:{label:'Frequenz',unit:'Hz'},power_factor:{label:'Leistungsfaktor',unit:''}};
function energyActiveSeries(){const root=$('energySeriesControls');return root?[...root.querySelectorAll('input:checked')].map(x=>x.value):['power_w']}
function energyVisiblePoints(){if(!energyData)return[];const all=energyData.points||[];if(!all.length)return[];const lo=energyViewStart??all[0].ts,hi=energyViewEnd??all[all.length-1].ts;return all.filter(p=>p.ts>=lo&&p.ts<=hi)}
function energySeriesExtent(points,key){const vals=points.map(p=>Number(p[key])).filter(Number.isFinite);if(!vals.length)return null;let lo=Math.min(...vals),hi=Math.max(...vals);if(lo===hi){const pad=Math.max(1,Math.abs(lo)*.05);lo-=pad;hi+=pad}else{const pad=(hi-lo)*.08;lo-=pad;hi+=pad}return[lo,hi]}
function energyPath(points,key,x,y){let started=false,out='';for(const p of points){const value=Number(p[key]);if(!Number.isFinite(value)){started=false;continue}out+=(started?' L':'M')+x(p).toFixed(1)+','+y(value).toFixed(1);started=true}return out}
function energyResetZoom(){energyViewStart=null;energyViewEnd=null;renderEnergyChart()}
function energyZoomBy(factor,center=null){if(!energyData||(energyData.points||[]).length<2)return;const all=energyData.points,fullStart=all[0].ts,fullEnd=all[all.length-1].ts;const start=energyViewStart??fullStart,end=energyViewEnd??fullEnd,mid=center??((start+end)/2);let span=Math.max(30,(end-start)*factor);span=Math.min(fullEnd-fullStart,span);let nextStart=mid-span/2,nextEnd=mid+span/2;if(nextStart<fullStart){nextEnd+=fullStart-nextStart;nextStart=fullStart}if(nextEnd>fullEnd){nextStart-=nextEnd-fullEnd;nextEnd=fullEnd}energyViewStart=Math.max(fullStart,nextStart);energyViewEnd=Math.min(fullEnd,nextEnd);renderEnergyChart()}
function energyBindChart(){if(energyChartBound)return;const svg=$('energyChart');if(!svg)return;energyChartBound=true;const shell=svg.parentElement;shell.classList.add('energy-chart-shell');let tip=document.createElement('div');tip.id='energyTooltip';tip.className='energy-tooltip';shell.appendChild(tip);svg.addEventListener('wheel',e=>{e.preventDefault();if(!energyData)return;const r=svg.getBoundingClientRect(),ratio=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));const pts=energyVisiblePoints();if(!pts.length)return;const center=pts[0].ts+ratio*(pts[pts.length-1].ts-pts[0].ts);energyZoomBy(e.deltaY<0?.65:1.5,center)},{passive:false});svg.addEventListener('pointerdown',e=>{const pts=energyVisiblePoints();if(pts.length<2)return;svg.setPointerCapture(e.pointerId);energyDrag={x:e.clientX,start:energyViewStart??pts[0].ts,end:energyViewEnd??pts[pts.length-1].ts};shell.classList.add('grabbing')});svg.addEventListener('pointermove',e=>{if(energyDrag){const r=svg.getBoundingClientRect(),delta=(e.clientX-energyDrag.x)/Math.max(1,r.width)*(energyDrag.end-energyDrag.start);const all=energyData.points||[],fullStart=all[0].ts,fullEnd=all[all.length-1].ts,span=energyDrag.end-energyDrag.start;let ns=energyDrag.start-delta,ne=energyDrag.end-delta;if(ns<fullStart){ns=fullStart;ne=ns+span}if(ne>fullEnd){ne=fullEnd;ns=ne-span}energyViewStart=ns;energyViewEnd=ne;renderEnergyChart();return}energyShowTooltip(e)});const stop=()=>{energyDrag=null;shell.classList.remove('grabbing')};svg.addEventListener('pointerup',stop);svg.addEventListener('pointercancel',stop);svg.addEventListener('pointerleave',()=>{if(!energyDrag)tip.style.display='none'});svg.addEventListener('dblclick',energyResetZoom)}
function energyShowTooltip(e){const svg=$('energyChart'),tip=$('energyTooltip'),pts=energyVisiblePoints();if(!svg||!tip||!pts.length)return;const r=svg.getBoundingClientRect(),ratio=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),target=pts[0].ts+ratio*(pts[pts.length-1].ts-pts[0].ts);let nearest=pts[0];for(const p of pts)if(Math.abs(p.ts-target)<Math.abs(nearest.ts-target))nearest=p;const rows=energyActiveSeries().map(key=>{const m=energySeriesMeta[key],v=Number(nearest[key]);return Number.isFinite(v)?`<div>${m.label}: <b>${energyFmt(v,key==='current_a'||key==='power_factor'?2:1)} ${m.unit}</b></div>`:''}).join('');tip.innerHTML=`<strong>${new Date(nearest.ts*1000).toLocaleString('de-DE')}</strong>${rows||'<div>Keine Werte</div>'}`;tip.style.display='block';tip.style.left=Math.min(r.width-220,Math.max(8,e.clientX-r.left+14))+'px';tip.style.top=Math.max(8,e.clientY-r.top-20)+'px'}
function renderEnergyChart(){if(!energyData)return;energyBindChart();const svg=$('energyChart'),empty=$('energyChartEmpty'),pts=energyVisiblePoints(),series=energyActiveSeries();const valid=series.some(k=>pts.some(p=>Number.isFinite(Number(p[k]))));if(!pts.length||!valid){svg.style.display='none';empty.style.display='block';return}empty.style.display='none';svg.style.display='block';const W=1400,H=420,L=76,R=28,T=28,B=56,minTs=pts[0].ts,maxTs=pts[pts.length-1].ts||minTs+1,x=p=>L+(p.ts-minTs)/Math.max(1,maxTs-minTs)*(W-L-R);let out='';for(let i=0;i<=5;i++){const yy=T+i*(H-T-B)/5;out+=`<line class="energy-grid" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/>`}for(let i=0;i<7;i++){const idx=Math.min(pts.length-1,Math.round(i*(pts.length-1)/6)),xx=x(pts[idx]);out+=`<text class="energy-axis" x="${xx}" y="${H-18}" text-anchor="middle">${energyDate(pts[idx].ts,energyData.range)}</text>`}for(const key of series){const ext=energySeriesExtent(pts,key);if(!ext)continue;const y=v=>T+(1-(v-ext[0])/Math.max(.000001,ext[1]-ext[0]))*(H-T-B),path=energyPath(pts,key,x,y);if(path)out+=`<path class="energy-series-line energy-series-${key}" d="${path}"/>`}svg.innerHTML=out;const all=energyData.points||[],zoomed=all.length&&((energyViewStart??all[0].ts)>all[0].ts||(energyViewEnd??all[all.length-1].ts)<all[all.length-1].ts);$('energyZoomStatus').textContent=zoomed?new Date(minTs*1000).toLocaleString('de-DE')+' – '+new Date(maxTs*1000).toLocaleString('de-DE'):'Gesamter Zeitraum'}
'''

page = energy_history.runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<svg id="energyChart"', CONTROLS + '<svg id="energyChart"', 1)
# Phase-2-Funktionen werden direkt vor der bestehenden energyData-Definition
# eingesetzt. Die spätere Funktionsdeklaration renderEnergyChart wird durch die
# gleichnamige Phase-2-Deklaration im selben Script ersetzt.
old_start = "let energyData=null;\nfunction energyFmt"
new_start = "let energyData=null;\n" + JS + "\nfunction energyFmt"
page = page.replace(old_start, new_start, 1)
# Entfernt die alte statische renderEnergyChart-Funktion vollständig, damit nur
# die interaktive Implementierung verwendet wird.
old_marker = "function renderEnergyChart(){if(!energyData)return;const svg=$('energyChart')"
start = page.find(old_marker)
if start >= 0:
    end = page.find("\nasync function loadEnergyHistory()", start)
    if end >= 0:
        page = page[:start] + page[end + 1:]

energy_history.runtime.PAGE = page
energy_history.legacy.PAGE = page
