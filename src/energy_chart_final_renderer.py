#!/usr/bin/env python3
"""Finaler, robuster Renderer für die Energiehistorie.

Dieses Modul wird absichtlich zuletzt geladen. Es stellt sicher, dass die vom
Backend gelieferten historischen Punkte unabhängig von vorherigen UI-Modulen
sichtbar gezeichnet werden.
"""
from __future__ import annotations

import energy_history

SCRIPT = r'''
(function(){
  function fmt(value, digits){
    const n=Number(value);
    return Number.isFinite(n)?n.toLocaleString('de-DE',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'—';
  }
  function label(ts, range){
    const d=new Date(Number(ts)*1000);
    if(range==='today'||range==='yesterday') return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
    return d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'2-digit'});
  }
  window.renderEnergyChart=function(){
    if(typeof energyData==='undefined'||!energyData) return;
    const svg=document.getElementById('energyChart');
    const empty=document.getElementById('energyChartEmpty');
    if(!svg||!empty) return;
    const points=(energyData.points||[]).filter(p=>Number.isFinite(Number(p.power_w)));
    if(!points.length){svg.style.display='none';empty.style.display='block';return;}
    empty.style.display='none';svg.style.display='block';
    const W=1400,H=420,L=72,R=24,T=24,B=54;
    const values=points.map(p=>Number(p.power_w));
    let min=Math.min(...values),max=Math.max(...values);
    if(min===max){min=Math.max(0,min-1);max=max+1;}
    const start=Number(points[0].ts),end=Number(points[points.length-1].ts)||start+1;
    const x=p=>L+(Number(p.ts)-start)/Math.max(1,end-start)*(W-L-R);
    const y=p=>T+(1-(Number(p.power_w)-min)/Math.max(.000001,max-min))*(H-T-B);
    let out='';
    for(let i=0;i<=5;i++){
      const yy=T+i*(H-T-B)/5;
      const value=max-(max-min)*i/5;
      out+=`<line class="energy-grid" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/>`+
           `<text class="energy-axis" x="${L-8}" y="${yy+4}" text-anchor="end">${Math.round(value)} W</text>`;
    }
    for(let i=0;i<7;i++){
      const idx=Math.min(points.length-1,Math.round(i*(points.length-1)/6));
      const p=points[idx];
      out+=`<text class="energy-axis" x="${x(p)}" y="${H-17}" text-anchor="middle">${label(p.ts,energyData.range)}</text>`;
    }
    const type=(document.getElementById('energyChartType')||{}).value||'line';
    if(type==='bar'){
      const bw=Math.max(1,Math.min(18,(W-L-R)/points.length*.75));
      out+=points.map(p=>`<rect class="energy-bar" x="${x(p)-bw/2}" y="${y(p)}" width="${bw}" height="${H-B-y(p)}"><title>${label(p.ts,energyData.range)}: ${fmt(p.power_w,1)} W</title></rect>`).join('');
    }else{
      const path=points.map((p,i)=>`${i?'L':'M'}${x(p).toFixed(1)},${y(p).toFixed(1)}`).join(' ');
      out+=`<path class="energy-area" d="${path} L${x(points[points.length-1])},${H-B} L${x(points[0])},${H-B} Z"/>`;
      out+=`<path class="energy-line" d="${path}"/>`;
    }
    svg.innerHTML=out;
    const period=document.getElementById('energyPeriod');
    if(period) period.textContent=new Date(start*1000).toLocaleString('de-DE')+' – '+new Date(end*1000).toLocaleString('de-DE')+' · '+points.length.toLocaleString('de-DE')+' Punkte';
  };
  document.addEventListener('DOMContentLoaded',function(){
    if(typeof loadEnergyHistory==='function') loadEnergyHistory();
  });
})();
'''

page = energy_history.runtime.PAGE
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
energy_history.runtime.PAGE = page
energy_history.legacy.PAGE = page
