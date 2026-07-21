#!/usr/bin/env python3
"""Erweiterte WireGuard-Verwaltung für mehrere Peers und mobile Clients."""
from __future__ import annotations

from flask import Response, jsonify, request

import wireguard_runtime as wg_runtime
from wireguard_manager import CONFIG_PATH, atomic_json, load_config, public_config
from wireguard_peers import create_client, delete_peer, public_peers, qr_svg, save_peer

app = wg_runtime.app
legacy = wg_runtime.legacy
runtime = wg_runtime.runtime


@app.get('/_internal/wireguard/peers')
@legacy.login_required
def wireguard_peers_get() -> Response:
    return jsonify({'peers': public_peers()})


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


ADVANCED_SECTION = r'''
<section id="wireguardPeers" class="tab"><div class="toolbar"><div><h2>WireGuard-Peers</h2><div class="muted">Server-/Client-Modus, mehrere Gegenstellen und mobile Client-Konfigurationen</div></div><button onclick="loadWireGuardPeers()">Neu laden</button></div>
<div class="section two">
<div class="card"><h2>Betriebsart</h2><div class="form-grid"><div class="field"><label>Modus</label><select id="wgMode"><option value="client">Client</option><option value="server">Server</option></select></div><div class="field"><label>Listen-Port</label><input id="wgListenPort" type="number" min="1" max="65535" value="51820"></div><div class="field full"><label>Öffentlicher Endpoint</label><input id="wgPublicEndpoint" placeholder="vpn.example.de:51820"></div><div class="field full"><button onclick="saveWireGuardServerSettings()">Betriebsart speichern</button></div></div></div>
<div class="card"><h2>Neuen mobilen Client erzeugen</h2><div class="form-grid"><div class="field"><label>Name</label><input id="wgClientName" placeholder="Notebook Markus"></div><div class="field"><label>Client-IP/CIDR</label><input id="wgClientAddress" placeholder="10.20.30.10/32"></div><div class="field full"><label>Routen im Client</label><input id="wgClientAllowedIps" value="0.0.0.0/0"></div><div class="field full"><label>DNS im Client</label><input id="wgClientDns" placeholder="10.20.30.1"></div><div class="field full"><button onclick="createWireGuardClient()">Client erzeugen</button></div></div></div>
</div>
<div class="section"><h3>Konfigurierte Peers</h3><div id="wgPeerList">Noch nicht geladen.</div></div>
<div class="section two"><div class="card"><h2>Erzeugte Client-Konfiguration</h2><p class="muted">Der private Schlüssel wird nur in dieser neu erzeugten Konfiguration angezeigt. Speichere sie sofort sicher.</p><textarea id="wgGeneratedConfig" rows="18" style="width:100%" readonly></textarea><div class="section"><button class="secondary" onclick="downloadWireGuardClient()">Als .conf herunterladen</button> <button onclick="showWireGuardQr()">QR-Code anzeigen</button></div></div><div class="card"><h2>QR-Code</h2><div id="wgQrCode" class="muted">Noch kein QR-Code erzeugt.</div></div></div>
</section>
'''

ADVANCED_JS = r'''
let wgPeers=[];
async function loadWireGuardPeers(){try{const [p,c]=await Promise.all([api('/_internal/wireguard/peers'),api('/_internal/wireguard')]);wgPeers=p.peers||[];const cfg=c.config||{};val('wgMode',cfg.mode||'client');val('wgListenPort',cfg.listen_port||51820);val('wgPublicEndpoint',cfg.public_endpoint||'');renderWireGuardPeers()}catch(e){notice(e.message,false)}}
function renderWireGuardPeers(){const box=$('wgPeerList');box.innerHTML=wgPeers.length?wgPeers.map(p=>`<div class="card"><div class="toolbar"><div><strong>${esc(p.name)}</strong><div class="muted">${esc(p.allowed_ips||'')}</div></div><span class="badge ${p.enabled!==false?'ok':'warn'}">${p.enabled!==false?'Aktiv':'Deaktiviert'}</span></div><div class="status-row"><span>Public Key</span><code>${esc(p.public_key||'')}</code></div><div class="status-row"><span>Endpoint</span><strong>${esc(p.endpoint||'—')}</strong></div><div class="section"><button class="secondary" onclick="toggleWireGuardPeer('${p.id}',${p.enabled===false})">${p.enabled===false?'Aktivieren':'Deaktivieren'}</button> <button class="danger" onclick="removeWireGuardPeer('${p.id}')">Löschen</button></div></div>`).join(''):'Noch keine zusätzlichen Peers vorhanden.'}
async function saveWireGuardServerSettings(){try{const d=await api('/_internal/wireguard/server-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:$('wgMode').value,listen_port:Number($('wgListenPort').value||51820),public_endpoint:$('wgPublicEndpoint').value.trim()})});notice(d.message);loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function createWireGuardClient(){try{const endpoint=$('wgPublicEndpoint').value.trim();const d=await api('/_internal/wireguard/client/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('wgClientName').value.trim(),client_address:$('wgClientAddress').value.trim(),endpoint,allowed_ips:$('wgClientAllowedIps').value.trim(),dns:$('wgClientDns').value.trim()})});val('wgGeneratedConfig',d.config||'');$('wgQrCode').textContent='Client erzeugt. QR-Code kann jetzt angezeigt werden.';notice('Client und Peer wurden erzeugt.');loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function toggleWireGuardPeer(id,enabled){const p=wgPeers.find(x=>x.id===id);if(!p)return;try{await api('/_internal/wireguard/peers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...p,enabled,preshared_key:''})});notice('Peer aktualisiert.');loadWireGuardPeers()}catch(e){notice(e.message,false)}}
async function removeWireGuardPeer(id){if(!confirm('Diesen WireGuard-Peer wirklich löschen?'))return;try{const d=await api('/_internal/wireguard/peers/'+encodeURIComponent(id),{method:'DELETE'});notice(d.message);loadWireGuardPeers()}catch(e){notice(e.message,false)}}
function downloadWireGuardClient(){const text=$('wgGeneratedConfig').value;if(!text){notice('Noch keine Client-Konfiguration vorhanden.',false);return}const blob=new Blob([text],{type:'text/plain'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='powergateway-client.conf';a.click();URL.revokeObjectURL(a.href)}
async function showWireGuardQr(){const text=$('wgGeneratedConfig').value;if(!text){notice('Noch keine Client-Konfiguration vorhanden.',false);return}try{const r=await fetch('/_internal/wireguard/qr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:text})});if(!r.ok){const d=await r.json();throw new Error(d.error||'QR-Code fehlgeschlagen')}const svg=await r.text();$('wgQrCode').innerHTML=svg}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'wireguardPeers\',this)">WireGuard-Peers</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', ADVANCED_SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='wireguardPeers')loadWireGuardPeers();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', ADVANCED_JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
