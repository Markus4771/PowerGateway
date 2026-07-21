#!/usr/bin/env python3
"""Zusätzliche WebGUI-Funktionen für PowerGateway 0.9.6."""
from __future__ import annotations

import json
from typing import Any

import webapp_runtime as runtime
import wireguard_manager
from flask import Response, jsonify
from setup_assistant import diagnostics, serial_devices, setup_check

app = runtime.app
legacy = runtime.legacy


@app.get('/_internal/setup-status')
@legacy.login_required
def setup_status() -> Response:
    application = runtime._application_config(False)
    network = legacy.read_json(legacy.NETWORK_STATUS_PATH)
    status = legacy.read_json(legacy.DATA_DIR / 'status.json')
    wireguard = wireguard_manager.load_config()
    return jsonify(setup_check(application, network, status, wireguard))


@app.get('/_internal/meter/serial-devices')
@legacy.login_required
def meter_serial_devices() -> Response:
    return jsonify({'devices': serial_devices()})


@app.get('/_internal/system-details')
@legacy.login_required
def system_details() -> Response:
    return jsonify(diagnostics())


page = legacy.PAGE
page = page.replace(
    '<button onclick="showTab(\'users\',this)">Benutzer</button>',
    '<button onclick="showTab(\'setup\',this)">Einrichtung</button><button onclick="showTab(\'users\',this)">Benutzer</button>',
)
page = page.replace(
    '<section id="users" class="tab">',
    '''<section id="setup" class="tab"><div class="toolbar"><div><h2>Einrichtungsstatus</h2><div class="muted">Alle wichtigen Verbindungen und Funktionen auf einen Blick.</div></div><button onclick="loadSetupStatus()">Neu prüfen</button></div><div id="setupCards" class="grid"></div><div class="section two"><div class="card"><h2>USB-SML-Geräte</h2><div id="serialDevices">Noch nicht geprüft.</div><div class="section"><button class="secondary" onclick="loadSerialDevices()">Leseköpfe suchen</button></div></div><div class="card"><h2>Systemzustand</h2><div id="systemDetails">Noch nicht geprüft.</div><div class="section"><button class="secondary" onclick="loadSystemDetails()">System prüfen</button></div></div></div></section><section id="users" class="tab">''',
)
page = page.replace(
    "if(id==='network')loadNetwork();if(id==='users')loadUsers();if(id==='meter'||id==='mqtt')loadApplication()",
    "if(id==='network')loadNetwork();if(id==='setup'){loadSetupStatus();loadSerialDevices();loadSystemDetails()}if(id==='users')loadUsers();if(id==='meter'||id==='mqtt')loadApplication()",
)
page = page.replace(
    'refresh();setInterval(refresh,5000);',
    '''async function loadSetupStatus(){try{const d=await api('/_internal/setup-status');$('setupCards').innerHTML=(d.items||[]).map(x=>card(x.label,x.ok?'Fertig':'Prüfen',x.ok?'ok':'warn')).join('')}catch(e){notice(e.message,false)}}
async function loadSerialDevices(){try{const d=await api('/_internal/meter/serial-devices');const items=d.devices||[];$('serialDevices').innerHTML=items.length?items.map(x=>`<div class="status-row"><div><strong>${esc(x.name)}</strong><div class="muted">${esc(x.path)}</div></div><button class="secondary" onclick="val('meterDevice',${JSON.stringify(x.path)});showTab('meter',document.querySelectorAll('.nav button')[1])">Übernehmen</button></div>`).join(''):'Keine USB-SML-Geräte gefunden.'}catch(e){$('serialDevices').textContent=e.message}}
function bytes(v){const u=['B','KB','MB','GB','TB'];let i=0,n=Number(v||0);while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`}
async function loadSystemDetails(){try{const d=await api('/_internal/system-details');$('systemDetails').innerHTML=[['Gerät',d.hostname],['Kernel',d.kernel],['Temperatur',d.temperature_c===null?'nicht verfügbar':`${d.temperature_c} °C`],['Systemlast',(d.load||[]).join(' / ')],['Speicher frei',bytes(d.disk_free)],['WireGuard',d.commands?.wg?'installiert':'fehlt'],['NetworkManager',d.commands?.nmcli?'installiert':'fehlt']].map(x=>`<div class="status-row"><span>${esc(x[0])}</span><strong>${esc(x[1])}</strong></div>`).join('')}catch(e){$('systemDetails').textContent=e.message}}
refresh();setInterval(refresh,5000);''',
)
legacy.PAGE = page
