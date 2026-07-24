#!/usr/bin/env python3
"""WebAPI für Status, Logs und Steuerung des SSH-Tunneldienstes."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from flask import Response, jsonify

import homeassistant_runtime as connector
from homeassistant_connector import load_config, validate_config

app = connector.app
legacy = connector.legacy
runtime = connector.runtime
STATUS_PATH = Path('/var/lib/powergateway/ha_tunnel_status.json')
SERVICE = 'powergateway-ha-tunnel.service'


def _run(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args=args, returncode=124, stdout=exc.stdout or '', stderr='Zeitüberschreitung bei der Dienststeuerung')
    except OSError as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout='', stderr=str(exc))


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return _run(['sudo', '-n', '/usr/bin/systemctl', *args, SERVICE])


def _service_state() -> dict:
    active = _run(['/usr/bin/systemctl', 'is-active', SERVICE], 5)
    enabled = _run(['/usr/bin/systemctl', 'is-enabled', SERVICE], 5)
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


def _validate_start() -> str | None:
    try:
        config = validate_config(load_config())
    except ValueError as exc:
        return str(exc)
    if not config.get('enabled'):
        return 'Die Home-Assistant-Verbindung ist nicht aktiviert.'
    if config.get('mode') not in {'ssh_mqtt', 'reverse_ssh_mqtt'}:
        return 'Als Verbindungsart ist kein SSH-Tunnel ausgewählt.'
    return None


@app.get('/_internal/ssh-tunnel/status')
@legacy.login_required
def ssh_tunnel_status() -> Response:
    return jsonify(_service_state())


@app.post('/_internal/ssh-tunnel/start')
@legacy.login_required
def ssh_tunnel_start() -> Response:
    error = _validate_start()
    if error:
        return jsonify({'ok': False, 'message': error, 'status': _service_state()}), 400
    result = _systemctl('enable', '--now')
    message = result.stderr.strip() or result.stdout.strip() or 'SSH-Tunnel wurde gestartet.'
    return jsonify({'ok': result.returncode == 0, 'message': message, 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.post('/_internal/ssh-tunnel/restart')
@legacy.login_required
def ssh_tunnel_restart() -> Response:
    error = _validate_start()
    if error:
        return jsonify({'ok': False, 'message': error, 'status': _service_state()}), 400
    result = _systemctl('restart')
    message = result.stderr.strip() or result.stdout.strip() or 'SSH-Tunnel wurde neu gestartet.'
    return jsonify({'ok': result.returncode == 0, 'message': message, 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.post('/_internal/ssh-tunnel/stop')
@legacy.login_required
def ssh_tunnel_stop() -> Response:
    result = _systemctl('disable', '--now')
    message = result.stderr.strip() or result.stdout.strip() or 'SSH-Tunnel wurde gestoppt.'
    return jsonify({'ok': result.returncode == 0, 'message': message, 'status': _service_state()}), 200 if result.returncode == 0 else 500


@app.get('/_internal/ssh-tunnel/logs')
@legacy.login_required
def ssh_tunnel_logs() -> Response:
    result = _run(['/usr/bin/journalctl', '-u', SERVICE, '-n', '100', '--no-pager', '-o', 'short-iso'], 10)
    return jsonify({'ok': result.returncode == 0, 'logs': result.stdout[-30000:], 'error': result.stderr.strip()})


page = runtime.PAGE
page = page.replace(
    '<pre id="hacResult">Noch nicht geprüft.</pre></div>',
    '<pre id="hacResult">Noch nicht geprüft.</pre><div class="section"><h3>SSH-Tunneldienst</h3><div id="sshTunnelState" class="muted">Noch nicht geprüft.</div><div class="toolbar"><button class="secondary" onclick="sshTunnelAction(\'start\')">Starten</button><button class="secondary" onclick="sshTunnelAction(\'restart\')">Neu starten</button><button class="secondary" onclick="sshTunnelAction(\'stop\')">Stoppen</button><button class="secondary" onclick="loadSshTunnelLogs()">Logs</button></div><pre id="sshTunnelLogs" style="max-height:260px;overflow:auto">Noch nicht geladen.</pre></div></div>',
)
page = page.replace(
    'async function loadHaConnector(){',
    "async function loadSshTunnelStatus(){try{const d=await api('/_internal/ssh-tunnel/status');$('sshTunnelState').innerHTML=`<div class=\"status-row\"><span>Dienst</span><strong>${d.active?'Aktiv':'Inaktiv'}</strong></div><div class=\"status-row\"><span>Autostart</span><strong>${d.enabled?'Aktiv':'Inaktiv'}</strong></div><div class=\"status-row\"><span>Zustand</span><strong>${esc(d.active_state||'unbekannt')}</strong></div><pre>${esc(JSON.stringify(d.detail||{},null,2))}</pre>`}catch(e){$('sshTunnelState').textContent=e.message}}\nasync function sshTunnelAction(action){try{const d=await api('/_internal/ssh-tunnel/'+action,{method:'POST'});notice(d.message,d.ok!==false);await loadSshTunnelStatus();if(action!=='stop')await loadSshTunnelLogs()}catch(e){notice(e.message,false);await loadSshTunnelStatus()}}\nasync function loadSshTunnelLogs(){try{const d=await api('/_internal/ssh-tunnel/logs');$('sshTunnelLogs').textContent=d.logs||d.error||'Keine Einträge.'}catch(e){$('sshTunnelLogs').textContent=e.message}}\nasync function loadHaConnector(){",
)
page = page.replace(
    "if(id==='haConnector')loadHaConnector();",
    "if(id==='haConnector'){loadHaConnector();loadSshTunnelStatus();}",
)
runtime.PAGE = page
legacy.PAGE = page
