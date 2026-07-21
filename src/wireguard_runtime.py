#!/usr/bin/env python3
"""WireGuard-Erweiterung für die PowerGateway-WebGUI."""
from __future__ import annotations

from flask import Response, jsonify, request

import webapp as legacy
import webapp_runtime as runtime
from wireguard_manager import (
    CONFIG_PATH,
    atomic_json,
    export_conf,
    generate_keys,
    generate_preshared_key,
    import_conf,
    load_config,
    load_status,
    public_config,
    validate_config,
)

app = runtime.app

WIREGUARD_SECTION = r'''
<section id="wireguard" class="tab"><div class="toolbar"><div><h2>WireGuard</h2><div class="muted">VPN-Client für sicheren Fernzugriff</div></div><button onclick="saveWireGuard()">Speichern und anwenden</button></div>
<div id="wireguardCards" class="grid"></div>
<div class="section two">
<div class="card"><h2>Tunnel</h2><div class="form-grid">
<label class="check full"><input id="wgEnabled" type="checkbox"> WireGuard aktivieren</label>
<label class="check full"><input id="wgAutostart" type="checkbox"> Automatisch beim Start verbinden</label>
<div class="field"><label>Tunnelname</label><input id="wgInterface" value="wg0"></div>
<div class="field"><label>MTU</label><input id="wgMtu" type="number" min="576" max="9000"></div>
<div class="field full"><label>Tunnel-IP/CIDR</label><input id="wgAddress" placeholder="10.20.30.2/24"></div>
<div class="field full"><label>DNS-Server</label><input id="wgDns" placeholder="10.20.30.1"></div>
</div></div>
<div class="card"><h2>Schlüssel</h2><div class="form-grid">
<div class="field full"><label>Privater Schlüssel</label><input id="wgPrivateKey" type="password" placeholder="Leer = vorhandenen Schlüssel behalten"></div>
<div class="field full"><label>Öffentlicher Schlüssel</label><input id="wgPublicKey" readonly></div>
<div class="field"><button class="secondary" onclick="generateWireGuardKeys()">Schlüsselpaar erzeugen</button></div>
<div class="field"><button class="secondary" onclick="generateWireGuardPsk()">Preshared Key erzeugen</button></div>
</div></div></div>
<div class="section two">
<div class="card"><h2>Gegenstelle</h2><div class="form-grid">
<div class="field full"><label>Name</label><input id="wgPeerName"></div>
<div class="field full"><label>Öffentlicher Schlüssel der Gegenstelle</label><input id="wgPeerPublicKey"></div>
<div class="field full"><label>Preshared Key (optional)</label><input id="wgPresharedKey" type="password" placeholder="Leer = vorhandenen Schlüssel behalten"></div>
<div class="field full"><label>Endpoint</label><input id="wgEndpoint" placeholder="vpn.example.de:51820"></div>
<div class="field full"><label>AllowedIPs (Komma)</label><input id="wgAllowedIps" placeholder="192.168.178.0/24, 10.0.0.0/24"></div>
<div class="field"><label>Persistent Keepalive</label><input id="wgKeepalive" type="number" min="0" max="65535"></div>
</div></div>
<div class="card"><h2>Import und Export</h2><div class="form-grid">
<div class="field full"><label>WireGuard-.conf importieren</label><input id="wgImportFile" type="file" accept=".conf,text/plain"></div>
<div class="field"><button class="secondary" onclick="importWireGuard()">Importieren</button></div>
<div class="field"><a class="button secondary" href="/_internal/wireguard/export">Konfiguration herunterladen</a></div>
</div><p class="muted">Ein Import aktiviert den Tunnel nicht automatisch. Prüfe die Werte und speichere anschließend.</p></div></div>
</section>
'''

WIREGUARD_JS = r'''
async function loadWireGuard(){try{const d=await api('/_internal/wireguard'),c=d.config||{},p=c.peer||{},s=d.status||{};chk('wgEnabled',c.enabled);chk('wgAutostart',c.autostart!==false);val('wgInterface',c.interface||'wg0');val('wgAddress',c.address||'');val('wgDns',c.dns||'');val('wgMtu',c.mtu||1420);val('wgPrivateKey','');val('wgPublicKey',c.public_key||'');val('wgPeerName',p.name||'VPN-Gegenstelle');val('wgPeerPublicKey',p.public_key||'');val('wgPresharedKey','');val('wgEndpoint',p.endpoint||'');val('wgAllowedIps',p.allowed_ips||'');val('wgKeepalive',p.persistent_keepalive??25);const hs=s.latest_handshake?new Date(s.latest_handshake*1000).toLocaleString():'Noch keiner';$('wireguardCards').innerHTML=[card('Status',s.state||'unbekannt',s.active?'ok':'bad'),card('Tunnel',s.interface||c.interface||'wg0'),card('Endpoint',s.endpoint||p.endpoint||'—'),card('Letzter Handshake',hs),card('Empfangen',formatBytes(s.received_bytes||0)),card('Gesendet',formatBytes(s.sent_bytes||0))].join('')}catch(e){notice(e.message,false)}}
function formatBytes(v){const n=Number(v||0);if(n<1024)return `${n} B`;if(n<1048576)return `${(n/1024).toFixed(1)} KiB`;if(n<1073741824)return `${(n/1048576).toFixed(1)} MiB`;return `${(n/1073741824).toFixed(2)} GiB`}
async function saveWireGuard(){const body={enabled:$('wgEnabled').checked,autostart:$('wgAutostart').checked,interface:$('wgInterface').value.trim()||'wg0',address:$('wgAddress').value.trim(),dns:$('wgDns').value.trim(),mtu:Number($('wgMtu').value||1420),private_key:$('wgPrivateKey').value.trim(),public_key:$('wgPublicKey').value.trim(),peer:{name:$('wgPeerName').value.trim(),public_key:$('wgPeerPublicKey').value.trim(),preshared_key:$('wgPresharedKey').value.trim(),endpoint:$('wgEndpoint').value.trim(),allowed_ips:$('wgAllowedIps').value.trim(),persistent_keepalive:Number($('wgKeepalive').value||0)}};try{const d=await api('/_internal/wireguard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});notice(d.message);setTimeout(loadWireGuard,3000)}catch(e){notice(e.message,false)}}
async function generateWireGuardKeys(){try{const d=await api('/_internal/wireguard/keys',{method:'POST'});val('wgPrivateKey',d.private_key);val('wgPublicKey',d.public_key);notice('Neues Schlüsselpaar erzeugt. Zum Übernehmen noch speichern.')}catch(e){notice(e.message,false)}}
async function generateWireGuardPsk(){try{const d=await api('/_internal/wireguard/psk',{method:'POST'});val('wgPresharedKey',d.preshared_key);notice('Preshared Key erzeugt. Zum Übernehmen noch speichern.')}catch(e){notice(e.message,false)}}
async function importWireGuard(){const f=$('wgImportFile').files[0];if(!f){notice('Bitte zuerst eine .conf-Datei auswählen.',false);return}try{const d=await api('/_internal/wireguard/import',{method:'POST',headers:{'Content-Type':'text/plain'},body:await f.text()}),c=d.config,p=c.peer||{};chk('wgEnabled',false);val('wgAddress',c.address);val('wgDns',c.dns);val('wgMtu',c.mtu);val('wgPrivateKey',d.private_key||'');val('wgPublicKey',c.public_key);val('wgPeerName',p.name);val('wgPeerPublicKey',p.public_key);val('wgPresharedKey',d.preshared_key||'');val('wgEndpoint',p.endpoint);val('wgAllowedIps',p.allowed_ips);val('wgKeepalive',p.persistent_keepalive);notice('Konfiguration importiert. Bitte prüfen und speichern.')}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'network\',this)">Netzwerk</button>', '<button onclick="showTab(\'network\',this)">Netzwerk</button><button onclick="showTab(\'wireguard\',this)">WireGuard</button>')
page = page.replace('<section id="users"', WIREGUARD_SECTION + '<section id="users"')
page = page.replace("if(id==='network')loadNetwork();", "if(id==='network')loadNetwork();if(id==='wireguard')loadWireGuard();")
page = page.replace('refresh();setInterval(refresh,5000);', WIREGUARD_JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page


@app.get('/_internal/wireguard')
@legacy.login_required
def get_wireguard() -> Response:
    return jsonify({"config": public_config(load_config()), "status": load_status()})


@app.post('/_internal/wireguard')
@legacy.login_required
def set_wireguard() -> Response:
    supplied = request.get_json(silent=True)
    try:
        config = validate_config(supplied, load_config())
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    current = load_config()
    if not str(supplied.get("private_key", "")).strip():
        config["private_key"] = current.get("private_key", "")
        config["public_key"] = current.get("public_key", config.get("public_key", ""))
    if not str(supplied.get("peer", {}).get("preshared_key", "")).strip():
        config["peer"]["preshared_key"] = current.get("peer", {}).get("preshared_key", "")
    atomic_json(CONFIG_PATH, config)
    return jsonify({"ok": True, "message": "WireGuard-Konfiguration gespeichert und wird angewendet."})


@app.post('/_internal/wireguard/keys')
@legacy.login_required
def wireguard_keys() -> Response:
    try:
        private_key, public_key = generate_keys()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"private_key": private_key, "public_key": public_key})


@app.post('/_internal/wireguard/psk')
@legacy.login_required
def wireguard_psk() -> Response:
    try:
        value = generate_preshared_key()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"preshared_key": value})


@app.post('/_internal/wireguard/import')
@legacy.login_required
def wireguard_import() -> Response:
    text = request.get_data(as_text=True)
    if len(text) > 65536:
        return jsonify({"error": "Die Konfigurationsdatei ist zu groß."}), 400
    try:
        config = import_conf(text)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    safe = public_config(config)
    return jsonify({"config": safe, "private_key": config.get("private_key", ""), "preshared_key": config.get("peer", {}).get("preshared_key", "")})


@app.get('/_internal/wireguard/export')
@legacy.login_required
def wireguard_export() -> Response:
    config = load_config()
    if not config.get("private_key"):
        return Response("Noch keine vollständige WireGuard-Konfiguration vorhanden.\n", status=400, mimetype="text/plain")
    filename = f"{config.get('interface', 'wg0')}.conf"
    return Response(export_conf(config), mimetype="text/plain", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
