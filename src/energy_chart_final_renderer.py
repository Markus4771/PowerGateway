#!/usr/bin/env python3
"""Finaler robuster Renderer fuer Energiehistorie mit Zoom und Pan."""
from __future__ import annotations

import energy_history

SCRIPT = r'''
(function(){
  let viewStart=null,viewEnd=null,drag=null,bound=false;
  function fmt(value,digits){const n=Number(value);return Number.isFinite(n)?n.toLocaleString('de-DE',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'—'}
  function label(ts,range){const d=new Date(Number(ts)*1000);if(range==='today'||range==='yesterday')return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'2-digit'})}
  function allPoints(){return (typeof energyData!=='undefined'&&energyData&&Array.isArray(energyData.points))?energyData.points.filter(p=>Number.isFinite(Number(p.power_w))):[]}
  function visiblePoints(){const all=allPoints();if(!all.length)return[];const lo=viewStart??Number(all[0].ts),hi=viewEnd??Number(all[all.length-1].ts);return all.filter(p=>Number(p.ts)>=lo&&Number(p.ts)<=hi)}
  function fullBounds(){const all=allPoints();return all.length?[Number(all[0].ts),Number(all[all.length-1].ts)]:[0,0]}
  function clamp(start,end){const [fs,fe]=fullBounds();if(fe<=fs)return[fs,fe];let span=Math.min(fe-fs,Math.max(10,end-start));let s=start,e=s+span;if(s<fs){s=fs;e=s+span}if(e>fe){e=fe;s=e-span}return[Math.max(fs,s),Math.min(fe,e)]}
  window.energyZoomBy=function(factor,center=null){const all=allPoints();if(all.length<2)return;const [fs,fe]=fullBounds();const s=viewStart??fs,e=viewEnd??fe,mid=center??((s+e)/2);const span=Math.min(fe-fs,Math.max(10,(e-s)*factor));[viewStart,viewEnd]=clamp(mid-span/2,mid+span/2);window.renderEnergyChart()};
  window.energyResetZoom=function(){viewStart=null;viewEnd=null;window.renderEnergyChart()};
  function bind(){if(bound)return;const svg=document.getElementById('energyChart');if(!svg)return;bound=true;svg.style.touchAction='none';svg.addEventListener('wheel',function(ev){ev.preventDefault();const pts=visiblePoints();if(pts.length<2)return;const r=svg.getBoundingClientRect();const ratio=Math.max(0,Math.min(1,(ev.clientX-r.left)/Math.max(1,r.width)));const center=Number(pts[0].ts)+ratio*(Number(pts[pts.length-1].ts)-Number(pts[0].ts));window.energyZoomBy(ev.deltaY<0?0.65:1.5,center)},{passive:false});svg.addEventListener('dblclick',function(){window.energyResetZoom()});svg.addEventListener('pointerdown',function(ev){const pts=visiblePoints();if(pts.length<2)return;svg.setPointerCapture(ev.pointerId);drag={x:ev.clientX,start:viewStart??Number(pts[0].ts),end:viewEnd??Number(pts[pts.length-1].ts)}});svg.addEventListener('pointermove',function(ev){if(!drag)return;const r=svg.getBoundingClientRect();const delta=(ev.clientX-drag.x)/Math.max(1,r.width)*(drag.end-drag.start);[viewStart,viewEnd]=clamp(drag.start-delta,drag.end-delta);window.renderEnergyChart()});const stop=function(){drag=null};svg.addEventListener('pointerup',stop);svg.addEventListener('pointercancel',stop)}
  window.renderEnergyChart=function(){
    if(typeof energyData==='undefined'||!energyData)return;
    const svg=document.getElementById('energyChart'),empty=document.getElementById('energyChartEmpty');if(!svg||!empty)return;bind();
    const all=allPoints(),points=visiblePoints();if(!points.length){svg.style.display='none';empty.style.display='block';return}empty.style.display='none';svg.style.display='block';
    const W=1400,H=420,L=72,R=24,T=24,B=54,values=points.map(p=>Number(p.power_w));let min=Math.min(...values),max=Math.max(...values);if(min===max){min=Math.max(0,min-1);max=max+1}
    const start=Number(points[0].ts),end=Number(points[points.length-1].ts)||start+1,x=p=>L+(Number(p.ts)-start)/Math.max(1,end-start)*(W-L-R),y=p=>T+(1-(Number(p.power_w)-min)/Math.max(.000001,max-min))*(H-T-B);let out='';
    for(let i=0;i<=5;i++){const yy=T+i*(H-T-B)/5,value=max-(max-min)*i/5;out+=`<line class="energy-grid" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text class="energy-axis" x="${L-8}" y="${yy+4}" text-anchor="end">${Math.round(value)} W</text>`}
    for(let i=0;i<7;i++){const idx=Math.min(points.length-1,Math.round(i*(points.length-1)/6)),p=points[idx];out+=`<text class="energy-axis" x="${x(p)}" y="${H-17}" text-anchor="middle">${label(p.ts,energyData.range)}</text>`}
    const type=(document.getElementById('energyChartType')||{}).value||'line';if(type==='bar'){const bw=Math.max(1,Math.min(18,(W-L-R)/points.length*.75));out+=points.map(p=>`<rect class="energy-bar" x="${x(p)-bw/2}" y="${y(p)}" width="${bw}" height="${H-B-y(p)}"><title>${label(p.ts,energyData.range)}: ${fmt(p.power_w,1)} W</title></rect>`).join('')}else{const path=points.map((p,i)=>`${i?'L':'M'}${x(p).toFixed(1)},${y(p).toFixed(1)}`).join(' ');out+=`<path class="energy-area" d="${path} L${x(points[points.length-1])},${H-B} L${x(points[0])},${H-B} Z"/><path class="energy-line" d="${path}"/>`}
    svg.innerHTML=out;const zoomed=all.length&&points.length<all.length,status=document.getElementById('energyZoomStatus');if(status)status.textContent=zoomed?new Date(start*1000).toLocaleString('de-DE')+' – '+new Date(end*1000).toLocaleString('de-DE'):'Gesamter Zeitraum';const period=document.getElementById('energyPeriod');if(period)period.textContent=new Date(start*1000).toLocaleString('de-DE')+' – '+new Date(end*1000).toLocaleString('de-DE')+' · '+points.length.toLocaleString('de-DE')+' Punkte';
  };
  document.addEventListener('DOMContentLoaded',function(){if(typeof loadEnergyHistory==='function')loadEnergyHistory()});
})();
'''

page = energy_history.runtime.PAGE
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
energy_history.runtime.PAGE = page
energy_history.legacy.PAGE = page
