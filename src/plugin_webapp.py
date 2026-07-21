#!/usr/bin/env python3
"""Webanwendung mit Plugin-API und Modulübersicht."""
from __future__ import annotations

from flask import Response, jsonify

import webapp_features as features
import wireguard_advanced  # registriert Peer-API und erweitert die WebGUI
from plugin_runtime import manager, module_status

app = features.app
legacy = features.legacy
runtime = features.runtime


@app.get('/_internal/modules')
@legacy.login_required
def modules_status() -> Response:
    return jsonify(module_status())


@app.get('/_internal/modules/diagnostics')
@legacy.login_required
def modules_diagnostics() -> Response:
    result = manager.diagnostics()
    result['events'] = module_status()['events']
    return jsonify(result)


page = runtime.PAGE
page = page.replace(
    '<button onclick="showTab(\'users\',this)">Benutzer</button>',
    '<button onclick="showTab(\'modules\',this)">Module</button><button onclick="showTab(\'users\',this)">Benutzer</button>',
)
page = page.replace(
    '<section id="users" class="tab">',
    '''<section id="modules" class="tab"><div class="toolbar"><div><h2>Module</h2><div class="muted">Status der modular eingebundenen PowerGateway-Funktionen.</div></div><button onclick="loadModules()">Neu prüfen</button></div><div id="moduleCards" class="grid"></div><div class="section"><h3>Ereignisse</h3><pre id="moduleEvents" style="max-height:360px;overflow:auto">Noch nicht geladen.</pre></div><div class="section"><button class="secondary" onclick="loadModuleDiagnostics()">Vollständige Moduldiagnose</button><pre id="moduleDiagnostics" style="max-height:420px;overflow:auto">Noch nicht geladen.</pre></div></section><section id="users" class="tab">''',
)
page = page.replace(
    "if(id==='users')loadUsers();",
    "if(id==='modules')loadModules();if(id==='users')loadUsers();",
)
page = page.replace(
    'refresh();setInterval(refresh,5000);',
    '''async function loadModules(){try{const d=await api('/_internal/modules');$('moduleCards').innerHTML=(d.plugins||[]).map(p=>{const details=p.details||{};const ok=p.state!=='error'&&details.ok!==false;return `<div class="card"><div class="toolbar"><div><h3>${esc(p.name)}</h3><div class="muted">${esc(p.plugin_id)} · Version ${esc(p.version)}</div></div><span class="badge ${ok?'ok':'bad'}">${ok?'Bereit':'Fehler'}</span></div><div class="status-row"><span>Status</span><strong>${esc(p.state)}</strong></div><pre style="max-height:180px;overflow:auto">${esc(JSON.stringify(details,null,2))}</pre></div>`}).join('');$('moduleEvents').textContent=JSON.stringify(d.events||[],null,2)}catch(e){notice(e.message,false)}}
async function loadModuleDiagnostics(){try{const d=await api('/_internal/modules/diagnostics');$('moduleDiagnostics').textContent=JSON.stringify(d,null,2)}catch(e){$('moduleDiagnostics').textContent=e.message;notice(e.message,false)}}
refresh();setInterval(refresh,5000);''',
)
runtime.PAGE = page
legacy.PAGE = page
