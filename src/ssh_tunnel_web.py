#!/usr/bin/env python3
"""WebAPI für Status, Logs und Steuerung des SSH-Tunneldienstes."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flask import Response, jsonify

import homeassistant_web as connector

app = connector.app
legacy = connector.legacy
runtime = connector.runtime
STATUS_PATH = Path('/var/lib/powergateway/ha_tunnel_status.json')
SERVICE = 'powergateway-ha-tunnel.service'


def _run(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _service_state() -> dict:
    active = _run(['systemctl', 'is-active', SERVICE], 5)
    enabled = _run(['systemctl', 'is-enabled', SERVICE], 5)
    try:
        detail = json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        detail = {}
    return {
        'active': active.stdout.strip() == 'active',
        'active_state': active.stdout.strip() or active.stderr.strip() or 'unknown',
        'enabled': enabled.stdout.strip() == 'enabled',
        'enabled_state': enabled.stdout.strip() or enabled.stderr.strip() or 'unknown',
        'detail': detail,
    }


@app.get('/_internal/ssh-tunnel/status')
@legacy.login_required
def ssh_tunnel_status() -> Response:
    return jsonify(_service_state())


@app.post('/_internal/ssh-tunnel/start')
@legacy.login_required
def ssh_tunnel_start() -> Response:
    result = _run(['systemctl', 'enable', '--now', SERVICE])
    return jsonify({'ok': result.returncode == 0, 'message': result.stderr.strip() or 'SSH-Tunnel wurde gestartet.', 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.post('/_internal/ssh-tunnel/restart')
@legacy.login_required
def ssh_tunnel_restart() -> Response:
    result = _run(['systemctl', 'restart', SERVICE])
    return jsonify({'ok': result.returncode == 0, 'message': result.stderr.strip() or 'SSH-Tunnel wurde neu gestartet.', 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.post('/_internal/ssh-tunnel/stop')
@legacy.login_required
def ssh_tunnel_stop() -> Response:
    result = _run(['systemctl', 'disable', '--now', SERVICE])
    return jsonify({'ok': result.returncode == 0, 'message': result.stderr.strip() or 'SSH-Tunnel wurde gestoppt.', 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.get('/_internal/ssh-tunnel/logs')
@legacy.login_required
def ssh_tunnel_logs() -> Response:
    result = _run(['journalctl', '-u', SERVICE, '-n', '100', '--no-pager', '-o', 'short-iso'], 10)
    return jsonify({'ok': result.returncode == 0, 'logs': result.stdout[-30000:], 'error': result.stderr.strip()})


page = runtime.PAGE
page = page.replace(
    '<pre id="hacResult">Noch nicht geprüft.</pre></div>',
    '<pre id="hacResult">Noch nicht geprüft.</pre><div class="section"><h3>SSH-Tunneldienst</h3><div id="sshTunnelState" class="muted">Noch nicht geprüft.</div><div class="toolbar"><button class="secondary" onclick="sshTunnelAction(\'start\')">Starten</button><button class="secondary" onclick="sshTunnelAction(\'restart\')">Neu starten</button><button class="secondary" onclick="sshTunnelAction(\'stop\')">Stoppen</button><button class="secondary" onclick="loadSshTunnelLogs()">Logs</button></div><pre id="sshTunnelLogs" style="max-height:260px;overflow:auto">Noch nicht geladen.</pre></div></div>',
)
page = page.replace(
    'async function loadHaConnector(){',
    "async function loadSshTunnelStatus(){try{const d=await api('/_internal/ssh-tunnel/status');$('sshTunnelState').innerHTML=`<div class=\"status-row\"><span>Dienst</span><strong>${d.active?'Aktiv':'Inaktiv'}</strong></div><div class=\"status-row\"><span>Autostart</span><strong>${d.enabled?'Aktiv':'Inaktiv'}</strong></div><pre>${esc(JSON.stringify(d.detail||{},null,2))}</pre>`}catch(e){$('sshTunnelState').textContent=e.message}}\nasync function sshTunnelAction(action){try{const d=await api('/_internal/ssh-tunnel/'+action,{method:'POST'});notice(d.message,d.ok!==false);await loadSshTunnelStatus()}catch(e){notice(e.message,false)}}\nasync function loadSshTunnelLogs(){try{const d=await api('/_internal/ssh-tunnel/logs');$('sshTunnelLogs').textContent=d.logs||d.error||'Keine Einträge.'}catch(e){$('sshTunnelLogs').textContent=e.message}}\nasync function loadHaConnector(){",
)
page = page.replace(
    "if(id==='haConnector')loadHaConnector();",
    "if(id==='haConnector'){loadHaConnector();loadSshTunnelStatus();}",
)
runtime.PAGE = page
legacy.PAGE = page
