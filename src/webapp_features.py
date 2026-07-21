#!/usr/bin/env python3
"""Zusätzliche WebGUI-Funktionen für PowerGateway 0.9.7."""
from __future__ import annotations

from typing import Any

import wireguard_manager
import wireguard_runtime as wg_runtime
from flask import Response, jsonify, request
from mqtt_assistant import capture_messages, connection_test, flatten_json
from runtime_config import load_runtime
from setup_assistant import diagnostics, serial_devices, setup_check

runtime = wg_runtime.runtime
app = wg_runtime.app
legacy = wg_runtime.legacy


def _mqtt_payload(supplied: Any) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Ungültige MQTT-Einstellungen.")
    current = load_runtime().get("mqtt", {})
    password = str(supplied.get("password", ""))
    if not password:
        password = str(current.get("password", ""))
    return {
        "host": str(supplied.get("host", "")).strip(),
        "port": supplied.get("port", 1883),
        "username": str(supplied.get("username", "")).strip(),
        "password": password,
        "tls": bool(supplied.get("tls")),
        "ca_file": str(supplied.get("ca_file", "")).strip(),
    }


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


@app.post('/_internal/mqtt-assistant/test')
@legacy.login_required
def mqtt_assistant_test() -> Response:
    try:
        result = connection_test(_mqtt_payload(request.get_json(silent=True)))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(result)


@app.post('/_internal/mqtt-assistant/topics')
@legacy.login_required
def mqtt_assistant_topics() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        messages = capture_messages(
            _mqtt_payload(supplied),
            topic_filter=str(supplied.get('topic_filter', '#')).strip() or '#',
            timeout=8.0,
        )
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'messages': messages, 'count': len(messages)})


@app.post('/_internal/mqtt-assistant/message')
@legacy.login_required
def mqtt_assistant_message() -> Response:
    supplied = request.get_json(silent=True) or {}
    topic = str(supplied.get('topic', '')).strip()
    if not topic:
        return jsonify({'error': 'Bitte zuerst ein Topic angeben oder auswählen.'}), 400
    try:
        messages = capture_messages(_mqtt_payload(supplied), topic_filter=topic, timeout=10.0, max_messages=1)
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    if not messages:
        return jsonify({'error': 'Innerhalb von 10 Sekunden wurde keine Nachricht empfangen.'}), 408
    message = messages[-1]
    message['fields'] = flatten_json(message.get('json')) if message.get('json') is not None else []
    return jsonify(message)


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
    '<div class="field full"><label>Eingangs-Topic</label><input id="sourceTopic" placeholder="tele/Stromzaehler/SENSOR"></div>',
    '''<div class="field"><label>MQTT-Server</label><input id="sourceMqttHost" placeholder="192.168.178.50"></div><div class="field"><label>Port</label><input id="sourceMqttPort" type="number" min="1" max="65535" value="1883"></div><div class="field"><label>Benutzername</label><input id="sourceMqttUsername"></div><div class="field"><label>Passwort</label><input id="sourceMqttPassword" type="password" placeholder="Leer = beibehalten"></div><label class="check"><input id="sourceMqttTls" type="checkbox"> TLS verwenden</label><div class="field"><label>CA-Datei</label><input id="sourceMqttCaFile" placeholder="/etc/ssl/certs/ca-certificates.crt"></div><div class="field full"><div class="toolbar"><button type="button" class="secondary" onclick="assistantTestMqtt()">Verbindung testen</button><button type="button" class="secondary" onclick="assistantFindTopics()">Topics suchen</button></div></div><div class="field full"><label>Eingangs-Topic</label><input id="sourceTopic" placeholder="tele/Stromzaehler/SENSOR"></div><div class="field full"><div id="mqttTopicResults" class="muted">Noch keine Topic-Suche.</div></div><div class="field full"><button type="button" class="secondary" onclick="assistantReceiveMessage()">MQTT-Nachricht empfangen und Felder erkennen</button></div><div class="field full"><pre id="mqttLiveMessage" style="max-height:260px;overflow:auto">Noch keine Nachricht empfangen.</pre></div><div class="field full"><div id="mqttFieldResults"></div></div>''',
)
page = page.replace(
    "if(id==='users')loadUsers();",
    "if(id==='setup'){loadSetupStatus();loadSerialDevices();loadSystemDetails()}if(id==='users')loadUsers();",
)
page = page.replace(
    'refresh();setInterval(refresh,5000);',
    '''async function loadSetupStatus(){try{const d=await api('/_internal/setup-status');$('setupCards').innerHTML=(d.items||[]).map(x=>card(x.label,x.ok?'Fertig':'Prüfen',x.ok?'ok':'warn')).join('')}catch(e){notice(e.message,false)}}
async function loadSerialDevices(){try{const d=await api('/_internal/meter/serial-devices');const items=d.devices||[];$('serialDevices').innerHTML=items.length?items.map(x=>`<div class="status-row"><div><strong>${esc(x.name)}</strong><div class="muted">${esc(x.path)}</div></div><button class="secondary" onclick="val('meterDevice',${JSON.stringify(x.path)});showTab('meter',document.querySelectorAll('.nav button')[1])">Übernehmen</button></div>`).join(''):'Keine USB-SML-Geräte gefunden.'}catch(e){$('serialDevices').textContent=e.message}}
function bytes(v){const u=['B','KB','MB','GB','TB'];let i=0,n=Number(v||0);while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`}
async function loadSystemDetails(){try{const d=await api('/_internal/system-details');$('systemDetails').innerHTML=[['Gerät',d.hostname],['Kernel',d.kernel],['Temperatur',d.temperature_c===null?'nicht verfügbar':`${d.temperature_c} °C`],['Systemlast',(d.load||[]).join(' / ')],['Speicher frei',bytes(d.disk_free)],['WireGuard',d.commands?.wg?'installiert':'fehlt'],['NetworkManager',d.commands?.nmcli?'installiert':'fehlt']].map(x=>`<div class="status-row"><span>${esc(x[0])}</span><strong>${esc(x[1])}</strong></div>`).join('')}catch(e){$('systemDetails').textContent=e.message}}
function assistantMqttBody(){return {host:$('sourceMqttHost').value.trim(),port:Number($('sourceMqttPort').value||1883),username:$('sourceMqttUsername').value.trim(),password:$('sourceMqttPassword').value,tls:$('sourceMqttTls').checked,ca_file:$('sourceMqttCaFile').value.trim(),topic:$('sourceTopic').value.trim()}}
async function assistantTestMqtt(){try{const d=await api('/_internal/mqtt-assistant/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(assistantMqttBody())});notice(d.message)}catch(e){notice(e.message,false)}}
async function assistantFindTopics(){try{$('mqttTopicResults').textContent='Lausche 8 Sekunden auf MQTT-Topics …';const d=await api('/_internal/mqtt-assistant/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...assistantMqttBody(),topic_filter:'#'})});$('mqttTopicResults').innerHTML=d.messages?.length?d.messages.map(m=>`<div class="status-row"><div><strong>${esc(m.topic)}</strong><div class="muted">${m.retained?'Retained · ':''}${esc((m.payload||'').slice(0,100))}</div></div><button type="button" class="secondary" onclick="val('sourceTopic',${JSON.stringify(m.topic)})">Auswählen</button></div>`).join(''):'Keine Nachrichten empfangen. Tasmota sendet möglicherweise erst beim nächsten TelePeriod.'}catch(e){$('mqttTopicResults').textContent=e.message;notice(e.message,false)}}
function assignMeterField(kind,path){if(kind==='power')val('powerPath',path);if(kind==='energy_import')val('importPath',path);if(kind==='energy_export')val('exportPath',path);notice(`Feld ${path} wurde übernommen.`)}
async function assistantReceiveMessage(){try{$('mqttLiveMessage').textContent='Warte bis zu 10 Sekunden auf eine Nachricht …';$('mqttFieldResults').innerHTML='';const d=await api('/_internal/mqtt-assistant/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(assistantMqttBody())});$('mqttLiveMessage').textContent=d.json?JSON.stringify(d.json,null,2):d.payload;const fields=d.fields||[];$('mqttFieldResults').innerHTML=fields.length?`<h3>Erkannte Zahlenfelder</h3>${fields.map(f=>`<div class="status-row"><div><strong>${esc(f.path)}</strong><div class="muted">Wert: ${esc(f.value)}${f.suggestion?' · Vorschlag vorhanden':''}</div></div><div>${f.suggestion?`<button type="button" onclick="assignMeterField('${f.suggestion}',${JSON.stringify(f.path)})">Vorschlag übernehmen</button>`:''}</div></div>`).join('')}`:'Keine numerischen JSON-Felder erkannt.'}catch(e){$('mqttLiveMessage').textContent=e.message;notice(e.message,false)}}
const loadApplicationBase=loadApplication;loadApplication=async function(){await loadApplicationBase();val('sourceMqttHost',$('mqttHost').value);val('sourceMqttPort',$('mqttPort').value||1883);val('sourceMqttUsername',$('mqttUsername').value);val('sourceMqttPassword','');chk('sourceMqttTls',$('mqttTls').checked);val('sourceMqttCaFile',$('mqttCaFile').value)};
const saveApplicationBase=saveApplication;saveApplication=async function(){if(['tasmota_mqtt','generic_mqtt'].includes($('meterSource').value)){val('mqttHost',$('sourceMqttHost').value);val('mqttPort',$('sourceMqttPort').value||1883);val('mqttUsername',$('sourceMqttUsername').value);val('mqttPassword',$('sourceMqttPassword').value);chk('mqttTls',$('sourceMqttTls').checked);val('mqttCaFile',$('sourceMqttCaFile').value)}return saveApplicationBase()};
refresh();setInterval(refresh,5000);''',
)
runtime.PAGE = page
legacy.PAGE = page
