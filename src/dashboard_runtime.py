#!/usr/bin/env python3
"""Zentrales Status-Dashboard und zusammengefasste PowerGateway-Diagnose."""
from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from flask import Response, jsonify

import webapp_features as features
from homeassistant_connector import diagnostics as ha_diagnostics, load_config as load_ha
from mqtt_assistant import connection_test
from noip_client import load_config as load_noip
from runtime_config import load_runtime

app = features.app
legacy = features.legacy
runtime = features.runtime
DATA_DIR = Path('/var/lib/powergateway')


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _run(args: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout='', stderr=str(exc))


def _item(key: str, label: str, state: str, message: str, details: Any = None) -> dict[str, Any]:
    return {'key': key, 'label': label, 'state': state, 'ok': state == 'ok', 'message': message, 'details': details}


def _guard(key: str, label: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = callback()
        result.setdefault('key', key)
        result.setdefault('label', label)
        return result
    except Exception as exc:
        return _item(key, label, 'error', str(exc))


def _internet() -> dict[str, Any]:
    started = time.monotonic()
    with socket.create_connection(('1.1.1.1', 53), timeout=4):
        latency = round((time.monotonic() - started) * 1000)
    return _item('internet', 'Internet', 'ok', f'Erreichbar ({latency} ms)', {'latency_ms': latency})


def _dns() -> dict[str, Any]:
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo('dynupdate.no-ip.com', 443, type=socket.SOCK_STREAM)})
    return _item('dns', 'DNS', 'ok', 'Namensauflösung funktioniert', {'addresses': addresses[:6]})


def _service(name: str, label: str, optional: bool = False) -> dict[str, Any]:
    result = _run(['/usr/bin/systemctl', 'is-active', name], 5)
    state = result.stdout.strip() or result.stderr.strip() or 'unknown'
    if state == 'active':
        return _item(name, label, 'ok', 'Dienst aktiv', {'systemd_state': state})
    if optional and state in {'inactive', 'unknown'}:
        return _item(name, label, 'disabled', 'Nicht aktiviert', {'systemd_state': state})
    return _item(name, label, 'error', f'Dienststatus: {state}', {'systemd_state': state})


def _meter() -> dict[str, Any]:
    status = _read_json(DATA_DIR / 'status.json')
    measurement = status.get('last_measurement') or status.get('measurement') or status.get('measurements')
    timestamp = status.get('last_message_at') or status.get('updated_at') or status.get('timestamp')
    if measurement:
        return _item('meter', 'Stromzähler', 'ok', 'Messwerte werden empfangen', {'updated_at': timestamp, 'measurement': measurement})
    source = load_runtime().get('source', {})
    if not source:
        return _item('meter', 'Stromzähler', 'disabled', 'Noch keine Datenquelle eingerichtet')
    return _item('meter', 'Stromzähler', 'warn', 'Datenquelle konfiguriert, aber noch keine Messwerte erkannt', {'source': source.get('type')})


def _mqtt() -> dict[str, Any]:
    config = load_runtime().get('mqtt', {})
    if not str(config.get('host', '')).strip():
        return _item('mqtt', 'MQTT', 'disabled', 'Noch nicht konfiguriert')
    result = connection_test(config)
    ok = bool(result.get('ok'))
    return _item('mqtt', 'MQTT', 'ok' if ok else 'error', result.get('message') or ('Verbindung erfolgreich' if ok else 'Verbindung fehlgeschlagen'), result)


def _homeassistant() -> dict[str, Any]:
    config = load_ha()
    if not config.get('enabled'):
        return _item('homeassistant', 'Home Assistant', 'disabled', 'Nicht aktiviert')
    result = ha_diagnostics(config)
    checks = result.get('checks', result)
    failed = [name for name, value in checks.items() if isinstance(value, dict) and value.get('ok') is False] if isinstance(checks, dict) else []
    return _item('homeassistant', 'Home Assistant', 'error' if failed else 'ok', 'Diagnose mit Fehlern' if failed else 'Verbindung konfiguriert', result)


def _wireguard() -> dict[str, Any]:
    config = _read_json(DATA_DIR / 'wireguard.json')
    enabled = bool(config.get('enabled'))
    result = _run(['/usr/bin/systemctl', 'is-active', 'wg-quick@wg0.service'], 5)
    active = result.stdout.strip() == 'active'
    if active:
        return _item('wireguard', 'WireGuard', 'ok', 'Tunnel aktiv')
    if not enabled:
        return _item('wireguard', 'WireGuard', 'disabled', 'Nicht aktiviert')
    return _item('wireguard', 'WireGuard', 'warn', 'Konfiguriert, aber Tunnel nicht aktiv')


def _ssh() -> dict[str, Any]:
    config = load_ha()
    selected = config.get('enabled') and config.get('mode') in {'ssh_mqtt', 'reverse_ssh_mqtt'}
    service = _service('powergateway-ha-tunnel.service', 'SSH-Tunnel', optional=not selected)
    detail = _read_json(DATA_DIR / 'ha_tunnel_status.json')
    service['details'] = {'service': service.get('details'), 'runtime': detail}
    return service


def _noip() -> dict[str, Any]:
    config = load_noip()
    status = _read_json(DATA_DIR / 'noip_status.json')
    if not config.get('enabled'):
        return _item('noip', 'No-IP', 'disabled', 'Nicht aktiviert', status)
    if status.get('ok'):
        return _item('noip', 'No-IP', 'ok', status.get('message', 'Hostname aktuell'), status)
    if status:
        return _item('noip', 'No-IP', 'error', status.get('message', 'Letzter Abgleich fehlgeschlagen'), status)
    return _item('noip', 'No-IP', 'warn', 'Aktiviert, aber noch nicht geprüft')


def build_dashboard(full: bool = False) -> dict[str, Any]:
    checks = [
        _guard('internet', 'Internet', _internet),
        _guard('dns', 'DNS', _dns),
        _guard('meter', 'Stromzähler', _meter),
        _guard('mqtt', 'MQTT', _mqtt),
        _guard('homeassistant', 'Home Assistant', _homeassistant),
        _guard('wireguard', 'WireGuard', _wireguard),
        _guard('ssh', 'SSH-Tunnel', _ssh),
        _guard('noip', 'No-IP', _noip),
        _service('powergateway.service', 'PowerGateway'),
        _service('powergateway-web.service', 'Weboberfläche'),
    ]
    counts = {state: sum(1 for item in checks if item['state'] == state) for state in ('ok', 'warn', 'error', 'disabled')}
    overall = 'error' if counts['error'] else ('warn' if counts['warn'] else 'ok')
    result: dict[str, Any] = {'overall': overall, 'counts': counts, 'items': checks, 'checked_at': int(time.time())}
    if full:
        result['system'] = {
            'uptime': _run(['/usr/bin/uptime', '-p'], 5).stdout.strip(),
            'disk': _run(['/bin/df', '-h', '/'], 5).stdout.strip(),
            'memory': _run(['/usr/bin/free', '-h'], 5).stdout.strip(),
            'failed_units': _run(['/usr/bin/systemctl', '--failed', '--no-legend', '--plain'], 8).stdout.strip(),
        }
    return result


@app.get('/_internal/dashboard')
@legacy.login_required
def dashboard_status() -> Response:
    return jsonify(build_dashboard(False))


@app.get('/_internal/dashboard/diagnostics')
@legacy.login_required
def dashboard_diagnostics() -> Response:
    return jsonify(build_dashboard(True))


SECTION = r'''
<section id="systemOverview" class="tab"><div class="toolbar"><div><h2>Systemübersicht</h2><div class="muted">Alle wichtigen PowerGateway-Verbindungen und Dienste auf einen Blick.</div></div><div><button class="secondary" onclick="loadCentralDiagnostics()">Alles prüfen</button> <button onclick="loadCentralDashboard()">Aktualisieren</button></div></div><div id="centralSummary" class="section muted">Noch nicht geprüft.</div><div id="centralCards" class="grid"></div><div class="section"><h3>Gesamtdiagnose</h3><pre id="centralDiagnostics" style="max-height:520px;overflow:auto">Die ausführliche Diagnose wird nur auf Anforderung ausgeführt.</pre></div></section>
'''

JS = r'''
function dashboardStateLabel(s){return s==='ok'?'Bereit':s==='warn'?'Prüfen':s==='disabled'?'Aus':'Fehler'}
function dashboardCard(x){const cls=x.state==='ok'?'ok':x.state==='error'?'bad':'warn';return `<div class="card"><div class="toolbar"><div><h3>${esc(x.label)}</h3><div class="muted">${esc(x.message||'')}</div></div><span class="badge ${cls}">${dashboardStateLabel(x.state)}</span></div>${x.details?`<details><summary>Details</summary><pre style="max-height:220px;overflow:auto">${esc(JSON.stringify(x.details,null,2))}</pre></details>`:''}</div>`}
async function loadCentralDashboard(){try{const d=await api('/_internal/dashboard');$('centralCards').innerHTML=(d.items||[]).map(dashboardCard).join('');const c=d.counts||{};$('centralSummary').innerHTML=`<strong>Gesamtstatus: ${dashboardStateLabel(d.overall)}</strong> · ${c.ok||0} bereit · ${c.warn||0} prüfen · ${c.error||0} Fehler · ${c.disabled||0} aus`;}catch(e){$('centralSummary').textContent=e.message;notice(e.message,false)}}
async function loadCentralDiagnostics(){try{$('centralDiagnostics').textContent='Diagnose läuft …';const d=await api('/_internal/dashboard/diagnostics');$('centralDiagnostics').textContent=JSON.stringify(d,null,2);$('centralCards').innerHTML=(d.items||[]).map(dashboardCard).join('');notice(d.overall==='error'?'Diagnose abgeschlossen: Fehler gefunden.':'Diagnose abgeschlossen.',d.overall!=='error')}catch(e){$('centralDiagnostics').textContent=e.message;notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'systemOverview\',this)">Übersicht</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='systemOverview')loadCentralDashboard();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
