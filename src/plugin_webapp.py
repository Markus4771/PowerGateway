#!/usr/bin/env python3
"""Webanwendung mit Plugin-API und Modulübersicht."""
from __future__ import annotations
from flask import Response, jsonify
import webapp_features as features
import wireguard_advanced
import homeassistant_runtime
import ssh_tunnel_web
import letsencrypt_web
import dashboard_runtime
import energy_history
import energy_collection_settings
import energy_history_professional
import daily_consumption
import export_center
import backup_center
import backup_center_v138
import network_diagnostics_runtime
import gateway_selector
import internet_manager
import measurement_export
import energy_resolution_v1312
import energy_chart_phase2
import energy_analysis_phase3
from plugin_runtime import manager, module_status
app=features.app
legacy=features.legacy
runtime=features.runtime
@app.get('/_internal/modules')
@legacy.login_required
def modules_status()->Response: return jsonify(module_status())
@app.get('/_internal/modules/diagnostics')
@legacy.login_required
def modules_diagnostics()->Response:
    result=manager.diagnostics(); result['events']=module_status()['events']; return jsonify(result)
page=runtime.PAGE
page=page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>','<button onclick="showTab(\'modules\',this)">Module</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page=page.replace('<section id="users" class="tab">','''<section id="modules" class="tab"><div class="toolbar"><div><h2>Module</h2><div class="muted">Status der modular eingebundenen PowerGateway-Funktionen.</div></div><button onclick="loadModules()">Neu prüfen</button></div><div id="moduleCards" class="grid"></div><div class="section"><h3>Ereignisse</h3><pre id="moduleEvents" style="max-height:360px;overflow:auto">Noch nicht geladen.</pre></div><div class="section"><button class="secondary" onclick="loadModuleDiagnostics()">Vollständige Moduldiagnose</button><pre id="moduleDiagnostics" style="max-height:420px;overflow:auto">Noch nicht geladen.</pre></div></section><section id="users" class="tab">''')
page=page.replace("if(id==='users')loadUsers();","if(id==='modules')loadModules();if(id==='users')loadUsers();")
page=page.replace('refresh();setInterval(refresh,5000);','''async function loadModules(){try{const d=await api('/_internal/modules');$('moduleCards').innerHTML=(d.plugins||[]).map(p=>{const details=p.details||{};const ok=p.state!=='error'&&details.ok!==false;return `<div class="card"><div class="toolbar"><div><h3>${esc(p.name)}</h3><div class="muted">${esc(p.plugin_id)} · Version ${esc(p.version)}</div></div><span class="badge ${ok?'ok':'bad'}">${ok?'Bereit':'Fehler'}</span></div><div class="status-row"><span>Status</span><strong>${esc(p.state)}</strong></div><pre style="max-height:180px;overflow:auto">${esc(JSON.stringify(details,null,2))}</pre></div>`}).join('');$('moduleEvents').textContent=JSON.stringify(d.events||[],null,2)}catch(e){notice(e.message,false)}}
async function loadModuleDiagnostics(){try{const d=await api('/_internal/modules/diagnostics');$('moduleDiagnostics').textContent=JSON.stringify(d,null,2)}catch(e){$('moduleDiagnostics').textContent=e.message;notice(e.message,false)}}
refresh();setInterval(refresh,5000);''')

UI_STYLE = r'''
:root{--sidebar:#102433;--sidebar-hover:#19384d;--accent:#1677ff;--surface:#fff;--canvas:#f3f6f9;--text:#17212b;--muted:#687784;--line:#dfe7ed;--ok:#14804a;--bad:#bd2c24;--warn:#ad6800}
body{background:var(--canvas);color:var(--text);min-height:100vh;padding-left:250px}
.head{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);color:var(--text);border-bottom:1px solid var(--line);padding:14px 28px;box-shadow:0 3px 12px #1730470b;backdrop-filter:blur(8px)}
.head h1{font-size:1.25rem}.head small{color:var(--muted);opacity:1}.head .button.secondary{background:#edf3f7;color:var(--text)}
.nav{position:fixed;inset:0 auto 0 0;width:250px;z-index:30;background:var(--sidebar);border:0;padding:88px 14px 20px;display:flex;flex-direction:column;gap:5px;overflow-y:auto;box-shadow:4px 0 18px #0c20301f}
.nav:before{content:'⚡  PowerGateway';position:absolute;top:0;left:0;right:0;height:70px;display:flex;align-items:center;padding:0 22px;color:#fff;font-weight:800;font-size:1.08rem;border-bottom:1px solid #ffffff18}
.nav button{width:100%;text-align:left;background:transparent;color:#d6e3ec;border:0;border-radius:9px;padding:12px 14px;font-size:.95rem;transition:.15s ease}
.nav button:hover{background:var(--sidebar-hover);color:#fff}.nav button.active{background:#fff;color:var(--sidebar);border:0;box-shadow:0 4px 12px #08172130}
.nav button:nth-child(1):before{content:'⌂  '}.nav button:nth-child(2):before{content:'✓  '}.nav button:nth-child(3):before{content:'⚙  '}.nav button:nth-child(4):before{content:'◈  '}.nav button:nth-child(5):before{content:'♙  '}.nav button:nth-child(6):before{content:'⌁  '}
.wrap{max-width:1600px;padding:24px 28px 44px;margin:0 auto}.grid{grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
.card{border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 18px #18384d0a;padding:19px}.card:hover{box-shadow:0 8px 24px #18384d12}
.value{font-size:1.45rem}.toolbar{flex-wrap:wrap}button,.button{border-radius:9px;padding:10px 14px;background:var(--accent)}button.secondary,.button.secondary{background:#eaf0f5;color:#233746}
input,select{border-radius:9px;padding:11px;border-color:#cbd7df}input:focus,select:focus{outline:3px solid #1677ff22;border-color:var(--accent)}
table{background:var(--surface);border-radius:10px;overflow:hidden}th{font-size:.8rem;text-transform:uppercase;letter-spacing:.035em;color:var(--muted)}
.notice{position:sticky;top:78px;z-index:18}.tab> .toolbar:first-child{background:var(--surface);padding:18px;border:1px solid var(--line);border-radius:14px}
.badge{display:inline-flex;align-items:center;border-radius:999px;padding:5px 9px;font-size:.78rem;font-weight:750;background:#eef3f6}.badge.ok{background:#e9f8ef}.badge.bad{background:#fff0ee}
@media(max-width:900px){body{padding-left:0;padding-bottom:70px}.head{padding:13px 16px}.nav{inset:auto 0 0 0;width:auto;height:64px;padding:7px;flex-direction:row;overflow-x:auto;overflow-y:hidden;box-shadow:0 -3px 18px #0c203024}.nav:before{display:none}.nav button{min-width:92px;text-align:center;padding:9px 8px;font-size:.76rem}.wrap{padding:16px}.two,.form-grid{grid-template-columns:1fr}.head{align-items:center;flex-direction:row}.head small{display:block;max-width:55vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
@media(max-width:560px){.head>div:last-child strong{display:none}.card{padding:15px}.grid{grid-template-columns:1fr}.toolbar>button{width:100%}}
'''
page=page.replace('</style></head>', UI_STYLE + '</style></head>')
page=page.replace('<section id="dashboard" class="tab active">','<section id="dashboard" class="tab active"><div class="toolbar"><div><h2>Systemübersicht</h2><div class="muted">Verbindungen, Zählerdaten und Dienste auf einen Blick.</div></div><button class="secondary" onclick="refresh()">Aktualisieren</button></div>')
runtime.PAGE=page
legacy.PAGE=page
