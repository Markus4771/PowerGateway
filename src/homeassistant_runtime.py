#!/usr/bin/env python3
"""WebGUI und API für Home Assistant, SSH-Tunnel und No-IP."""
from __future__ import annotations

import subprocess
from flask import Response, jsonify, request

import webapp_features as features
from homeassistant_connector import diagnostics as ha_diagnostics
from homeassistant_connector import generate_ssh_key, load_config as load_ha, public_config as public_ha, save_config as save_ha
from noip_client import diagnostics as noip_diagnostics
from noip_client import load_config as load_noip, load_history as load_noip_history, load_status as load_noip_status
from noip_client import public_config as public_noip, save_config as save_noip, update as update_noip

app = features.app
legacy = features.legacy
runtime = features.runtime
SERVICE = 'powergateway-ha-tunnel.service'


def _sync_tunnel_service(config: dict) -> dict:
    ssh_enabled = bool(config.get('enabled')) and config.get('mode') in {'ssh_mqtt', 'reverse_ssh_mqtt'}
    action = ['enable', '--now'] if ssh_enabled else ['disable', '--now']
    result = subprocess.run(['sudo', '-n', '/usr/bin/systemctl', *action, SERVICE], capture_output=True, text=True, timeout=20, check=False)
    return {'ok': result.returncode == 0, 'message': result.stderr.strip() or result.stdout.strip()}


@app.get('/_internal/homeassistant-connector')
@legacy.login_required
def connector_get() -> Response:
    return jsonify({'config': public_ha(load_ha()), 'noip': public_noip(load_noip()), 'noip_status': load_noip_status(), 'noip_history': load_noip_history(50)})


@app.post('/_internal/homeassistant-connector')
@legacy.login_required
def connector_save() -> Response:
    try:
        config = save_ha(request.get_json(silent=True) or {})
        service = _sync_tunnel_service(config)
    except (ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': service.get('ok', False), 'config': public_ha(config), 'service': service, 'message': 'Home-Assistant-Verbindung gespeichert.'})


@app.post('/_internal/homeassistant-connector/test')
@legacy.login_required
def connector_test() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        config = save_ha(supplied) if supplied else load_ha()
        return jsonify(ha_diagnostics(config))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400


@app.post('/_internal/homeassistant-connector/ssh-key')
@legacy.login_required
def connector_ssh_key() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        return jsonify(generate_ssh_key(str(supplied.get('identity_file', '')).strip() or None))
    except (ValueError, OSError) as exc:
        return jsonify({'error': str(exc)}), 400


@app.post('/_internal/noip')
@legacy.login_required
def noip_save() -> Response:
    try:
        config = save_noip(request.get_json(silent=True) or {})
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, 'config': public_noip(config), 'status': load_noip_status(), 'history': load_noip_history(50), 'message': 'No-IP-Einstellungen gespeichert.'})


@app.post('/_internal/noip/update')
@legacy.login_required
def noip_update() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        config = save_noip(supplied) if supplied else load_noip()
        result = update_noip(config, force=True)
    except (ValueError, OSError) as exc:
        return jsonify({'error': str(exc)}), 400
    result['history'] = load_noip_history(50)
    return jsonify(result), 200 if result.get('ok') else 400


@app.get('/_internal/noip/status')
@legacy.login_required
def noip_status() -> Response:
    return jsonify({'config': public_noip(load_noip()), 'status': load_noip_status(), 'history': load_noip_history(50)})


@app.get('/_internal/noip/diagnostics')
@legacy.login_required
def noip_diag() -> Response:
    return jsonify(noip_diagnostics())


SECTION = r'''
<section id="haConnector" class="tab"><div class="toolbar"><div><h2>Home Assistant & Remotezugriff</h2><div class="muted">MQTT direkt, über WireGuard oder über einen SSH-Tunnel.</div></div><button onclick="loadHaConnector()">Neu laden</button></div>
<div class="section two"><div class="card"><h2>Home-Assistant-Verbindung</h2><div class="form-grid"><label class="check"><input id="hacEnabled" type="checkbox"> Verbindung aktivieren</label><div class="field"><label>Verbindungsart</label><select id="hacMode"><option value="direct_mqtt">MQTT direkt</option><option value="wireguard_mqtt">WireGuard + MQTT</option><option value="ssh_mqtt">SSH-Tunnel + MQTT</option><option value="reverse_ssh_mqtt">Reverse-SSH + MQTT</option></select></div><div class="field"><label>Home Assistant Host/IP</label><input id="hacHaHost"></div><div class="field"><label>Home Assistant Port</label><input id="hacHaPort" type="number" value="8123"></div><div class="field"><label>MQTT Host/IP</label><input id="hacMqttHost"></div><div class="field"><label>MQTT Port</label><input id="hacMqttPort" type="number" value="1883"></div><div class="field"><label>SSH-/No-IP-Host</label><input id="hacSshHost"></div><div class="field"><label>SSH-Port</label><input id="hacSshPort" type="number" value="22"></div><div class="field"><label>SSH-Benutzer</label><input id="hacSshUser"></div><div class="field full"><label>SSH-Schlüsseldatei</label><input id="hacIdentity" value="/var/lib/powergateway/.ssh/id_ed25519"></div><div class="field"><label>Lokaler MQTT-Tunnelport</label><input id="hacLocalPort" type="number" value="18830"></div><div class="field"><label>Entfernter MQTT-Port</label><input id="hacRemotePort" type="number" value="1883"></div><div class="field full"><button onclick="saveHaConnector()">Speichern</button> <button class="secondary" onclick="testHaConnector()">Verbindung testen</button> <button class="secondary" onclick="createHaSshKey()">SSH-Schlüssel erzeugen</button></div></div><pre id="hacResult">Noch nicht geprüft.</pre></div>
<div class="card"><h2>No-IP DDNS</h2><div class="form-grid"><label class="check"><input id="noipEnabled" type="checkbox"> No-IP aktivieren</label><div class="field full"><label>No-IP-Hostname</label><input id="noipHostname"></div><div class="field"><label>Benutzername/DDNS-Key</label><input id="noipUsername"></div><div class="field"><label>Passwort/DDNS-Key-Passwort</label><input id="noipPassword" type="password" placeholder="Leer = beibehalten"></div><div class="field"><label>Update-Intervall (Minuten)</label><input id="noipInterval" type="number" min="5" value="10"></div><label class="check"><input id="noipIpv4" type="checkbox" checked> IPv4/A-Record aktualisieren</label><label class="check"><input id="noipIpv6" type="checkbox"> IPv6/AAAA-Record aktualisieren</label><label class="check full"><input id="noipRestartSsh" type="checkbox" checked> SSH-Tunnel bei geänderter IP neu starten</label><label class="check full"><input id="noipRestartWireguard" type="checkbox"> WireGuard bei geänderter IP neu starten</label><div class="field full"><button onclick="saveNoip()">Speichern</button> <button class="secondary" onclick="testNoip()">Jetzt aktualisieren</button> <button class="secondary" onclick="diagnoseNoip()">Diagnose</button></div></div><pre id="noipResult">Noch nicht geprüft.</pre><h3>Letzte Änderungen</h3><div id="noipHistory" class="muted">Noch keine Einträge.</div></div></div></section>
'''

JS = r'''
function fmtTs(v){return v?new Date(v*1000).toLocaleString():'—'}
function showNoipHistory(rows){$('noipHistory').innerHTML=(rows||[]).slice().reverse().map(x=>`<div class="status-row"><span>${esc(fmtTs(x.timestamp))}</span><strong>${x.ok?'OK':'Fehler'} · ${esc(x.status||'')}</strong><span>${esc(x.message||'')}</span></div>`).join('')||'Noch keine Einträge.'}
function showNoipStatus(s){const h=s.history;const copy={...s};delete copy.history;$('noipResult').textContent=JSON.stringify({...copy,last_attempt_text:fmtTs(copy.last_attempt_at),last_success_text:fmtTs(copy.last_success_at),next_update_text:fmtTs(copy.next_update_at)},null,2);if(h)showNoipHistory(h)}
async function loadHaConnector(){try{const d=await api('/_internal/homeassistant-connector'),c=d.config||{},n=d.noip||{};$('hacEnabled').checked=!!c.enabled;val('hacMode',c.mode||'direct_mqtt');val('hacHaHost',c.ha_host||'');val('hacHaPort',c.ha_port||8123);val('hacMqttHost',c.mqtt_host||'');val('hacMqttPort',c.mqtt_port||1883);val('hacSshHost',c.ssh_host||'');val('hacSshPort',c.ssh_port||22);val('hacSshUser',c.ssh_user||'');val('hacIdentity',c.identity_file||'');val('hacLocalPort',c.local_mqtt_port||18830);val('hacRemotePort',c.remote_mqtt_port||1883);$('noipEnabled').checked=!!n.enabled;val('noipHostname',n.hostname||'');val('noipUsername',n.username||'');val('noipPassword','');val('noipInterval',n.interval_minutes||10);$('noipIpv4').checked=n.ipv4_enabled!==false;$('noipIpv6').checked=!!n.ipv6_enabled;$('noipRestartSsh').checked=n.restart_ssh_on_ip_change!==false;$('noipRestartWireguard').checked=!!n.restart_wireguard_on_ip_change;showNoipStatus(d.noip_status||{});showNoipHistory(d.noip_history||[])}catch(e){notice(e.message,false)}}
function haPayload(){return {enabled:$('hacEnabled').checked,mode:$('hacMode').value,ha_host:$('hacHaHost').value.trim(),ha_port:Number($('hacHaPort').value),mqtt_host:$('hacMqttHost').value.trim(),mqtt_port:Number($('hacMqttPort').value),ssh_host:$('hacSshHost').value.trim(),ssh_port:Number($('hacSshPort').value),ssh_user:$('hacSshUser').value.trim(),identity_file:$('hacIdentity').value.trim(),local_mqtt_port:Number($('hacLocalPort').value),remote_mqtt_host:'127.0.0.1',remote_mqtt_port:Number($('hacRemotePort').value)}}
async function saveHaConnector(){try{const d=await api('/_internal/homeassistant-connector',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(haPayload())});notice(d.message,d.ok!==false)}catch(e){notice(e.message,false)}}
async function testHaConnector(){try{const d=await api('/_internal/homeassistant-connector/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(haPayload())});$('hacResult').textContent=JSON.stringify(d,null,2)}catch(e){$('hacResult').textContent=e.message;notice(e.message,false)}}
async function createHaSshKey(){try{const d=await api('/_internal/homeassistant-connector/ssh-key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity_file:$('hacIdentity').value.trim()})});$('hacResult').textContent='Öffentlichen Schlüssel auf dem SSH-Server in ~/.ssh/authorized_keys eintragen:\n\n'+d.public_key}catch(e){notice(e.message,false)}}
function noipPayload(){return {enabled:$('noipEnabled').checked,hostname:$('noipHostname').value.trim(),username:$('noipUsername').value.trim(),password:$('noipPassword').value,interval_minutes:Number($('noipInterval').value),ipv4_enabled:$('noipIpv4').checked,ipv6_enabled:$('noipIpv6').checked,restart_ssh_on_ip_change:$('noipRestartSsh').checked,restart_wireguard_on_ip_change:$('noipRestartWireguard').checked}}
async function saveNoip(){try{const d=await api('/_internal/noip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(noipPayload())});notice(d.message);val('noipPassword','');showNoipStatus(d.status||{});showNoipHistory(d.history||[])}catch(e){notice(e.message,false)}}
async function testNoip(){try{const r=await fetch('/_internal/noip/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(noipPayload())}),d=await r.json();showNoipStatus(d);if(!r.ok)throw new Error(d.error||d.message);notice(d.message)}catch(e){notice(e.message,false)}}
async function diagnoseNoip(){try{const d=await api('/_internal/noip/diagnostics');$('noipResult').textContent=JSON.stringify(d,null,2);showNoipHistory(d.history||[])}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'haConnector\',this)">Home Assistant</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='haConnector')loadHaConnector();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
