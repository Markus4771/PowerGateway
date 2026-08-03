#!/usr/bin/env python3
"""Garantiert eine funktionsfähige Energiegraphik unabhängig von älteren UI-Patches."""
from __future__ import annotations

import energy_history

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime

SCRIPT = r'''
(function(){
  function pgFmt(v,d){const n=Number(v);return Number.isFinite(n)?n.toLocaleString('de-DE',{maximumFractionDigits:d??1}):'–'}
  function pgDate(ts,range){const d=new Date(Number(ts)*1000);return ['today','yesterday'].includes(range)?d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'})}
  window.renderEnergyChart=function(){
    const data=window.energyData;
    const svg=document.getElementById('energyChart');
    const empty=document.getElementById('energyChartEmpty');
    if(!svg||!data)return;
    const all=Array.isArray(data.points)?data.points:[];
    const lo=Number.isFinite(window.energyViewStart)?window.energyViewStart:(all[0]?.ts);
    const hi=Number.isFinite(window.energyViewEnd)?window.energyViewEnd:(all[all.length-1]?.ts);
    const pts=all.filter(p=>Number(p.ts)>=lo&&Number(p.ts)<=hi);
    const root=document.getElementById('energySeriesControls');
    let series=root?[...root.querySelectorAll('input:checked')].map(x=>x.value):['power_w'];
    if(!series.length)series=['power_w'];
    const valid=series.some(k=>pts.some(p=>Number.isFinite(Number(p[k]))));
    if(!pts.length||!valid){svg.style.display='none';if(empty)empty.style.display='block';return}
    if(empty)empty.style.display='none';svg.style.display='block';
    const W=1400,H=420,L=76,R=28,T=28,B=56,minTs=Number(pts[0].ts),maxTs=Number(pts[pts.length-1].ts)||minTs+1;
    const x=p=>L+(Number(p.ts)-minTs)/Math.max(1,maxTs-minTs)*(W-L-R);
    const colors={power_w:'var(--accent)',voltage_v:'#14804a',current_a:'#ad6800',frequency_hz:'#7b3fc6',power_factor:'#bd2c24'};
    let out='';
    for(let i=0;i<=5;i++){const y=T+i*(H-T-B)/5;out+=`<line class="energy-grid" x1="${L}" y1="${y}" x2="${W-R}" y2="${y}"/>`}
    for(let i=0;i<7;i++){const idx=Math.min(pts.length-1,Math.round(i*(pts.length-1)/6)),p=pts[idx];out+=`<text class="energy-axis" x="${x(p)}" y="${H-18}" text-anchor="middle">${pgDate(p.ts,data.range)}</text>`}
    for(const key of series){
      const vals=pts.map(p=>Number(p[key])).filter(Number.isFinite);if(!vals.length)continue;
      let min=Math.min(...vals),max=Math.max(...vals);if(min===max){const pad=Math.max(1,Math.abs(min)*.05);min-=pad;max+=pad}else{const pad=(max-min)*.08;min-=pad;max+=pad}
      const y=v=>T+(1-(v-min)/Math.max(.000001,max-min))*(H-T-B);
      let path='',started=false;
      for(const p of pts){const v=Number(p[key]);if(!Number.isFinite(v)){started=false;continue}path+=(started?' L':'M')+x(p).toFixed(1)+','+y(v).toFixed(1);started=true}
      if(path)out+=`<path fill="none" stroke="${colors[key]||'var(--accent)'}" stroke-width="2.5" vector-effect="non-scaling-stroke" d="${path}"/>`;
    }
    svg.innerHTML=out;
    const status=document.getElementById('energyZoomStatus');if(status)status.textContent=(Number.isFinite(lo)&&Number.isFinite(hi))?new Date(lo*1000).toLocaleString('de-DE')+' – '+new Date(hi*1000).toLocaleString('de-DE'):'Gesamter Zeitraum';
  };
  window.addEventListener('error',e=>{if(String(e.message||'').includes('renderEnergyChart is not defined')){window.renderEnergyChart();}});
})();
'''

page = runtime.PAGE
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
runtime.PAGE = page
legacy.PAGE = page
