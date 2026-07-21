#!/usr/bin/env python3
"""Erweiterte WireGuard-Verwaltung für mehrere Peers und mobile Clients."""
from __future__ import annotations

from flask import Response, jsonify, request

import wireguard_runtime as wg_runtime
from wireguard_diagnostics import diagnose
from wireguard_manager import CONFIG_PATH, atomic_json, load_config, load_status, public_config
from wireguard_peers import create_client, delete_peer, next_client_address, public_peers, qr_svg, save_peer

app = wg_runtime.app
legacy = wg_runtime.legacy
runtime = wg_runtime.runtime


@app.get('/_internal/wireguard/peers')
@legacy.login_required
def wireguard_peers_get() -> Response:
    status = load_status()
    return jsonify({'peers': public_peers(status.get('peers', [])), 'status': status})


@app.post('/_internal/wireguard/peers')
@legacy.login_required
def wireguard_peers_save() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        peer = save_peer(supplied)
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    safe = dict(peer)
    safe['preshared_key'] = ''
    safe['has_preshared_key'] = bool(peer.get('preshared_key'))
    CONFIG_PATH.touch(exist_ok=True)
    return jsonify({'ok': True, 'peer': safe, 'message': 'Peer gespeichert. WireGuard wird neu angewendet.'})


@app.delete('/_internal/wireguard/peers/<peer_id>')
@legacy.login_required
def wireguard_peers_delete(peer_id: str) -> Response:
    if not delete_peer(peer_id):
        return jsonify({'error': 'Peer wurde nicht gefunden.'}), 404
    CONFIG_PATH.touch(exist_ok=True)
    return jsonify({'ok': True, 'message': 'Peer gelöscht. WireGuard wird neu angewendet.'})


@app.post('/_internal/wireguard/server-settings')
@legacy.login_required
def wireguard_server_settings() -> Response:
    supplied = request.get_json(silent=True) or {}
    config = load_config()
    mode = str(supplied.get('mode', 'client')).strip().lower()
    if mode not in {'client', 'server'}:
        return jsonify({'error': 'Ungültiger WireGuard-Modus.'}), 400
    try:
        listen_port = int(supplied.get('listen_port', 51820))
    except (TypeError, ValueError):
        return jsonify({'error': 'Ungültiger Listen-Port.'}), 400
    if listen_port < 1 or listen_port > 65535:
        return jsonify({'error': 'Listen-Port muss zwischen 1 und 65535 liegen.'}), 400
    config['mode'] = mode
    config['listen_port'] = listen_port
    config['public_endpoint'] = str(supplied.get('public_endpoint', '')).strip()
    atomic_json(CONFIG_PATH, config)
    return jsonify({'ok': True, 'config': public_config(config), 'message': 'Server-Einstellungen gespeichert.'})


@app.get('/_internal/wireguard/client/next-address')
@legacy.login_required
def wireguard_client_next_address() -> Response:
    try:
        address = next_client_address()
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'address': address})


@app.post('/_internal/wireguard/client/create')
@legacy.login_required
def wireguard_client_create() -> Response:
    supplied = request.get_json(silent=True) or {}
    try:
        result = create_client(
            name=str(supplied.get('name', 'Neuer Client')).strip() or 'Neuer Client',
            client_address=str(supplied.get('client_address', '')).strip(),
            endpoint=str(supplied.get('endpoint', '')).strip(),
            allowed_ips=str(supplied.get('allowed_ips', '0.0.0.0/0')).strip() or '0.0.0.0/0',
            dns=str(supplied.get('dns', '')).strip(),
            description=str(supplied.get('description', '')).strip(),
            group=str(supplied.get('group', '')).strip(),
            expires_at=str(supplied.get('expires_at', '')).strip(),
        )
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    CONFIG_PATH.touch(exist_ok=True)
    return jsonify(result)


@app.post('/_internal/wireguard/qr')
@legacy.login_required
def wireguard_qr() -> Response:
    supplied = request.get_json(silent=True) or {}
    text = str(supplied.get('config', ''))
    if not text:
        return jsonify({'error': 'Keine Client-Konfiguration vorhanden.'}), 400
    try:
        svg = qr_svg(text)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return Response(svg, mimetype='image/svg+xml')


@app.get('/_internal/wireguard/diagnostics')
@legacy.login_required
def wireguard_diagnostics() -> Response:
    return jsonify(diagnose())


ADVANCED_SECTION = r'''
<section id="wireguardPeers" class="tab"><div class="toolbar"><div><h2>WireGuard-Zentrale</h2><div class="muted">Server-/Client-Modus, Peers, QR-Codes, Live-Status und Diagnose</div></div><button onclick="loadWireGuardPeers()">Neu laden</button></div>
<div class="section two">
<div class="card"><h2>Betriebsart</h2><div class="form-grid"><div class="field"><label>Modus</label><select id="wgMode"><option value="client">Client</option><option value="server">Server</option></select></div><div class="field"><label>Listen-Port</label><input id="wgListenPort" type="number" min="1" max="65535" value="51820"></div><div class="field full"><label>Öffentlicher Endpoint</label><input id="wgPublicEndpoint" placeholder="vpn.example.de:51820"></div><div class="field full"><button onclick="saveWireGuardServerSettings()">Betriebsart speichern</button></div></div></div>
<div class="card"><h2>Neuen Client erzeugen</h2><div class="form-grid"><div class="field"><label>Name</label><input id="wgClientName" placeholder="Notebook Markus"></div><div class="field"><label>Gruppe</label><input id="wgClientGroup" placeholder="Außendienst"></div><div class="field full"><label>Beschreibung</label><input id="wgClientDescription" placeholder="Dienstnotebook"></div><div class="field"><label>Client-IP/CIDR</label><input id="wgClientAddress" placeholder="Leer = automatisch"></div><div class="field"><label>Ablaufdatum</label><input id="wgClientExpires" type="date"></div><div class="field full"><label>Routen im Client</label><input id="wgClientAllowedIps" value="0.0.0.0/0"></div><div class="field full"><label>DNS im Client</label><input id="wgClientDns" placeholder="10.20.30.1"></div><div class="field full"><button class="secondary" onclick="suggestWireGuardAddress()">Freie IP vorschlagen</button> <button onclick="createWireGuardClient()">Client erzeugen</button></div></div></div>
</div>
<div class="section"><div class="toolbar"><h3>Konfigurierte Peers</h3><button class="secondary" onclick="runWireGuardDiagnostics()">Diagnose starten</button></div><div id="wgPeerList">Noch nicht geladen.</div></div>
<div class="section two"><div class="card"><h2>Client-Konfiguration</h2><p class="muted">Der private Schlüssel wird nur hier angezeigt. Konfiguration sofort sicher speichern.</p><textarea id="wgGeneratedConfig" rows="18" style="width:100%" readonly></textarea><div class="section"><button class="secondary" onclick="downloadWireGuardClient()">Als .conf herunterladen</button> <button onclick="showWireGuardQr()">QR-Code anzeigen</button></div></div><div class="card"><h2>QR-Code</h2><div id="wgQrCode" class="muted">Noch kein QR-Code erzeugt.</div></div></div>
<div class="section"><h3>WireGuard-Diagnose</h3><div id="wgDiagnostics" class="muted">Noch nicht ausgeführt.</div></div>
</section>
'''

ADVANCED_JS = r'''
let wgPeers=[];
async function loadWireGuardPeers(){try{const [p,c]=await Promise.all([api('/_internal/wireguard/peers'),api('/_internal/wireguard')]);wgPeers=p.peers||[];const cfg=c.config||{};val('wgMode',cfg.mode||'client');val('wgListenPort',cfg.listen_port||51820);val('wgPublicEndpoint',cfg.public_endpoint||'');renderWireGuardPeers()}catch(e){notice(e.message,false)}}
function wgAgo(ts){if(!ts)return 'Noch nie';const s=Math.max(0,Math.floor(Date.now()/1000-ts));if(s<60)return `${s} Sek.`;if(s<3600)return `${Math.floor(s/60)} Min.`;if(s<86400)return `${Math.floor(s/3600)} Std.`;return `${Math.floor(s/86400)} Tage`}
function renderWireGuardPeers(){const box=$('wgPeerList');box.innerHTML=wgPeers.length?wgPeers.map(p=>{const r=p.runtime||{},online=p.online===true,expired=p.expired===true;return `<div class="card"><div class="toolbar"><div><strong>${esc(p.name)}</strong><div class="muted">${esc(p.group||'Ohne Gruppe')} · ${esc(p.allowed_ips||'')}</div></div><span class="badge ${expired?'bad':online?'ok':p.enabled!==false?'warn':'bad'}">${expired?'Abgelaufen':online?'Online':p.enabled!==false?'Offline':'Deaktiviert'}</span></div><div class="status-row"><span>Beschreibung</span><strong>${esc(p.description||'—')}</strong></div><div class="status-row"><span>Letzter Handshake</span><strong>${esc(wgAgo(r.latest_handshake))}</strong></div><div class="status-row"><span>Empfangen / Gesendet</span><strong>${formatBytes(r.received_bytes||0)} / ${formatBytes(r.sent_bytes||0)}</strong></div><div class="status-row"><span>Ablaufdatum</span><strong>${esc(p.expires_at||'Keines')}</strong></div><div class="section"><button class="secondary" onclick="editWireGuardPeer('${p.id}')">Bearbeiten</button> <button class="secondary" onclick="toggleWireGuardPeer('${p.id}',${p.enabled===false})">${p.enabled===false?'Aktivieren':'Deaktivieren'}</button> <button class="danger" onclick="removeWireGuardPeer('${p.id}')">Löschen</button></div></div>`}).join(''):'Noch keine zusätzlichen Peers vorhanden.'}
async function saveWireGuardServerSettings(){try{const d=await api('/_internal/wireguard/server-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:$('wgMode').value,listen_port:Number($('wgListenPort').value||51820),public_endpoint:$('wgPublicEndpoint').value.trim()})});notice(d.message);loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function suggestWireGuardAddress(){try{const d=await api('/_internal/wireguard/client/next-address');val('wgClientAddress',d.address)}catch(e){notice(e.message,false)}}
async function createWireGuardClient(){try{const d=await api('/_internal/wireguard/client/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('wgClientName').value.trim(),group:$('wgClientGroup').value.trim(),description:$('wgClientDescription').value.trim(),expires_at:$('wgClientExpires').value,client_address:$('wgClientAddress').value.trim(),endpoint:$('wgPublicEndpoint').value.trim(),allowed_ips:$('wgClientAllowedIps').value.trim(),dns:$('wgClientDns').value.trim()})});val('wgGeneratedConfig',d.config||'');val('wgClientAddress',d.client_address||'');$('wgQrCode').textContent='Client erzeugt. QR-Code kann angezeigt werden.';notice('Client und Peer wurden erzeugt.');loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function editWireGuardPeer(id){const p=wgPeers.find(x=>x.id===id);if(!p)return;const name=prompt('Peer-Name',p.name);if(name===null)return;const description=prompt('Beschreibung',p.description||'');if(description===null)return;const group=prompt('Gruppe',p.group||'');if(group===null)return;const allowed_ips=prompt('AllowedIPs',p.allowed_ips||'');if(allowed_ips===null)return;const expires_at=prompt('Ablaufdatum YYYY-MM-DD (leer = keines)',p.expires_at||'');if(expires_at===null)return;try{const d=await api('/_internal/wireguard/peers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,name,description,group,allowed_ips,expires_at,preshared_key:''})});notice(d.message);loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function toggleWireGuardPeer(id,enabled){const p=wgPeers.find(x=>x.id===id);if(!p)return;try{await api('/_internal/wireguard/peers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,enabled,preshared_key:''})});notice('Peer aktualisiert.');loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function removeWireGuardPeer(id){if(!confirm('Diesen WireGuard-Peer wirklich löschen?'))return;try{const d=await api('/_internal/wireguard/peers/'+encodeURIComponent(id),{method:'DELETE'});notice(d.message);loadWireGuardPeers()}catch(e){notice(e.message,false)}}
function downloadWireGuardClient(){const text=$('wgGeneratedConfig').value;if(!text){notice('Noch keine Client-Konfiguration vorhanden.',false);return}const blob=new Blob([text],{type:'text/plain'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='powergateway-client.conf';a.click();URL.revokeObjectURL(a.href)}
async function showWireGuardQr(){const text=$('wgGeneratedConfig').value;if(!text){notice('Noch keine Client-Konfiguration vorhanden.',false);return}try{const r=await fetch('/_internal/wireguard/qr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:text})});if(!r.ok){const d=await r.json();throw new Error(d.error||'QR-Code fehlgeschlagen')}const svg=await r.text();$('wgQrCode').innerHTML=svg}catch(e){notice(e.message,false)}}
async function runWireGuardDiagnostics(){try{$('wgDiagnostics').textContent='Diagnose läuft …';const d=await api('/_internal/wireguard/diagnostics');$('wgDiagnostics').innerHTML=(d.checks||[]).map(x=>`<div class="status-row"><div><strong>${esc(x.label)}</strong><div class="muted">${esc(x.message)}${x.recommendation?`<br>${esc(x.recommendation)}`:''}</div></div><span class="badge ${x.ok?'ok':'bad'}">${x.ok?'OK':'Prüfen'}</span></div>`).join('')}catch(e){$('wgDiagnostics').textContent=e.message;notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'wireguardPeers\',this)">WireGuard-Zentrale</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', ADVANCED_SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='wireguardPeers')loadWireGuardPeers();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', ADVANCED_JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
