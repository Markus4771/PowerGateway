#!/usr/bin/env python3
"""Zentrales Status-Dashboard und zusammengefasste PowerGateway-Diagnose."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sqlite3
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
ENERGY_DB = DATA_DIR / 'energy_history.sqlite3'


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


def _human_bytes(value: int | float) -> str:
    size = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


def _format_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f'{days} T')
    if hours or days:
        parts.append(f'{hours} Std')
    parts.append(f'{minutes} Min')
    return ' '.join(parts)


def _system_metrics() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    load_percent = round(load1 / cpu_count * 100, 1)

    meminfo: dict[str, int] = {}
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            key, value = line.split(':', 1)
            meminfo[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    total_mem = meminfo.get('MemTotal', 0)
    available_mem = meminfo.get('MemAvailable', 0)
    used_mem = max(0, total_mem - available_mem)
    memory_percent = round(used_mem / total_mem * 100, 1) if total_mem else None

    disk = shutil.disk_usage('/')
    disk_percent = round(disk.used / disk.total * 100, 1) if disk.total else 0.0

    temperature = None
    for path in (Path('/sys/class/thermal/thermal_zone0/temp'), Path('/sys/class/hwmon/hwmon0/temp1_input')):
        try:
            temperature = round(float(path.read_text().strip()) / 1000.0, 1)
            break
        except (OSError, ValueError):
            continue

    try:
        uptime_seconds = float(Path('/proc/uptime').read_text().split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0.0

    db_size = ENERGY_DB.stat().st_size if ENERGY_DB.exists() else 0
    sample_count = 0
    if ENERGY_DB.exists():
        try:
            with sqlite3.connect(f'file:{ENERGY_DB}?mode=ro', uri=True, timeout=2) as db:
                sample_count = int(db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0])
        except (sqlite3.Error, OSError, TypeError):
            sample_count = 0

    return {
        'cpu': {'load_percent': load_percent, 'load_1m': round(load1, 2), 'load_5m': round(load5, 2), 'load_15m': round(load15, 2), 'cores': cpu_count},
        'memory': {'used_bytes': used_mem, 'total_bytes': total_mem, 'percent': memory_percent, 'display': f'{_human_bytes(used_mem)} / {_human_bytes(total_mem)}' if total_mem else 'Nicht verfügbar'},
        'disk': {'used_bytes': disk.used, 'total_bytes': disk.total, 'free_bytes': disk.free, 'percent': disk_percent, 'display': f'{_human_bytes(disk.used)} / {_human_bytes(disk.total)}'},
        'temperature_c': temperature,
        'uptime_seconds': int(uptime_seconds),
        'uptime': _format_uptime(uptime_seconds),
        'database': {'path': str(ENERGY_DB), 'size_bytes': db_size, 'size': _human_bytes(db_size), 'samples': sample_count},
        'platform': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(), 'python': platform.python_version(), 'hostname': socket.gethostname()},
    }


def _network_metrics() -> dict[str, Any]:
    route = _run(['/usr/sbin/ip', '-j', 'route', 'show', 'default'], 5)
    if route.returncode != 0:
        route = _run(['/sbin/ip', '-j', 'route', 'show', 'default'], 5)
    routes: list[dict[str, Any]] = []
    try:
        routes = json.loads(route.stdout) if route.stdout.strip() else []
    except json.JSONDecodeError:
        routes = []
    default = routes[0] if routes else {}
    interface = default.get('dev')
    gateway = default.get('gateway')

    addresses: list[str] = []
    if interface:
        result = _run(['/usr/sbin/ip', '-j', 'address', 'show', 'dev', str(interface)], 5)
        if result.returncode != 0:
            result = _run(['/sbin/ip', '-j', 'address', 'show', 'dev', str(interface)], 5)
        try:
            data = json.loads(result.stdout) if result.stdout.strip() else []
            for entry in data:
                for info in entry.get('addr_info', []):
                    if info.get('scope') == 'global':
                        addresses.append(f"{info.get('local')}/{info.get('prefixlen')}")
        except json.JSONDecodeError:
            pass

    dns: list[str] = []
    try:
        for line in Path('/etc/resolv.conf').read_text(encoding='utf-8').splitlines():
            if line.startswith('nameserver '):
                dns.append(line.split(None, 1)[1].strip())
    except OSError:
        pass

    network_status = _read_json(DATA_DIR / 'network_status.json')
    return {'interface': interface, 'gateway': gateway, 'addresses': addresses, 'dns': dns, 'runtime': network_status}


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
    detail_result = _run(['/usr/bin/systemctl', 'show', name, '--property=ActiveEnterTimestamp,MainPID,MemoryCurrent,CPUUsageNSec', '--no-pager'], 5)
    details: dict[str, str] = {'systemd_state': state}
    for line in detail_result.stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            details[key] = value
    if state == 'active':
        return _item(name, label, 'ok', 'Dienst aktiv', details)
    if optional and state in {'inactive', 'unknown'}:
        return _item(name, label, 'disabled', 'Nicht aktiviert', details)
    return _item(name, label, 'error', f'Dienststatus: {state}', details)


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
    wg = _run(['/usr/bin/wg', 'show', 'wg0', 'dump'], 5)
    details: dict[str, Any] = {'configured': enabled}
    if wg.returncode == 0 and wg.stdout.strip():
        lines = wg.stdout.strip().splitlines()
        peers = []
        for line in lines[1:]:
            fields = line.split('\t')
            if len(fields) >= 8:
                peers.append({'endpoint': fields[2], 'allowed_ips': fields[3], 'latest_handshake': int(fields[4] or 0), 'received_bytes': int(fields[5] or 0), 'sent_bytes': int(fields[6] or 0), 'keepalive': fields[7]})
        details['peers'] = peers
    if active:
        return _item('wireguard', 'WireGuard', 'ok', 'Tunnel aktiv', details)
    if not enabled:
        return _item('wireguard', 'WireGuard', 'disabled', 'Nicht aktiviert', details)
    return _item('wireguard', 'WireGuard', 'warn', 'Konfiguriert, aber Tunnel nicht aktiv', details)


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
        _service('powergateway-energy-history.service', 'Energiehistorie', optional=True),
    ]
    counts = {state: sum(1 for item in checks if item['state'] == state) for state in ('ok', 'warn', 'error', 'disabled')}
    overall = 'error' if counts['error'] else ('warn' if counts['warn'] else 'ok')
    result: dict[str, Any] = {
        'overall': overall,
        'counts': counts,
        'items': checks,
        'checked_at': int(time.time()),
        'system_metrics': _guard('system', 'System', lambda: _item('system', 'System', 'ok', 'Systemwerte erfasst', _system_metrics()))['details'],
        'network_metrics': _guard('network', 'Netzwerk', lambda: _item('network', 'Netzwerk', 'ok', 'Netzwerkwerte erfasst', _network_metrics()))['details'],
    }
    if full:
        result['system'] = {
            'uptime': _run(['/usr/bin/uptime', '-p'], 5).stdout.strip(),
            'disk': _run(['/bin/df', '-h', '/'], 5).stdout.strip(),
            'memory': _run(['/usr/bin/free', '-h'], 5).stdout.strip(),
            'failed_units': _run(['/usr/bin/systemctl', '--failed', '--no-legend', '--plain'], 8).stdout.strip(),
            'kernel': _run(['/usr/bin/uname', '-a'], 5).stdout.strip(),
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
<section id="systemOverview" class="tab"><div class="toolbar"><div><h2>Systemübersicht</h2><div class="muted">Alle wichtigen PowerGateway-Verbindungen, Ressourcen und Dienste auf einen Blick.</div></div><div><button class="secondary" onclick="loadCentralDiagnostics()">Alles prüfen</button> <button onclick="loadCentralDashboard()">Aktualisieren</button></div></div><div id="centralSummary" class="section muted">Noch nicht geprüft.</div><div id="resourceCards" class="grid resource-cards"></div><div class="section"><h3>Verbindungen und Dienste</h3><div id="centralCards" class="grid"></div></div><div class="section"><h3>Gesamtdiagnose</h3><pre id="centralDiagnostics" style="max-height:520px;overflow:auto">Die ausführliche Diagnose wird nur auf Anforderung ausgeführt.</pre></div></section>
'''

STYLE = r'''
.resource-cards{margin:14px 0 22px}.resource-card .value{font-size:1.35rem}.resource-card progress{width:100%;height:9px;margin-top:10px}.resource-card .detail{font-size:.82rem;margin-top:7px;color:var(--muted)}
'''

JS = r'''
let centralDashboardTimer=null;
function dashboardStateLabel(s){return s==='ok'?'Bereit':s==='warn'?'Prüfen':s==='disabled'?'Aus':'Fehler'}
function dashboardCard(x){const cls=x.state==='ok'?'ok':x.state==='error'?'bad':'warn';return `<div class="card"><div class="toolbar"><div><h3>${esc(x.label)}</h3><div class="muted">${esc(x.message||'')}</div></div><span class="badge ${cls}">${dashboardStateLabel(x.state)}</span></div>${x.details?`<details><summary>Details</summary><pre style="max-height:220px;overflow:auto">${esc(JSON.stringify(x.details,null,2))}</pre></details>`:''}</div>`}
function metricCard(label,value,percent,detail){const p=percent===null||percent===undefined?'':`<progress max="100" value="${Math.max(0,Math.min(100,Number(percent)||0))}"></progress>`;return `<div class="card resource-card"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div>${p}<div class="detail">${esc(detail||'')}</div></div>`}
function renderResourceCards(d){const s=d.system_metrics||{},cpu=s.cpu||{},mem=s.memory||{},disk=s.disk||{},db=s.database||{},net=d.network_metrics||{};const temp=s.temperature_c===null||s.temperature_c===undefined?'Nicht verfügbar':Number(s.temperature_c).toLocaleString('de-DE',{maximumFractionDigits:1})+' °C';$('resourceCards').innerHTML=[metricCard('CPU-Last',(cpu.load_percent??'—')+' %',cpu.load_percent,`${cpu.cores||'—'} Kerne · Load ${cpu.load_1m??'—'}`),metricCard('Arbeitsspeicher',mem.percent===null||mem.percent===undefined?'—':mem.percent+' %',mem.percent,mem.display),metricCard('Systemspeicher',disk.percent+' %',disk.percent,disk.display),metricCard('CPU-Temperatur',temp,s.temperature_c?Math.min(100,Number(s.temperature_c)):null,s.uptime?'Laufzeit: '+s.uptime:''),metricCard('Energiedatenbank',db.size||'0 B',null,(db.samples||0).toLocaleString('de-DE')+' Messwerte'),metricCard('Aktives Netzwerk',net.interface||'Keine Verbindung',null,[...(net.addresses||[]),net.gateway?'Gateway '+net.gateway:''].filter(Boolean).join(' · '))].join('')}
async function loadCentralDashboard(){try{const d=await api('/_internal/dashboard');renderResourceCards(d);$('centralCards').innerHTML=(d.items||[]).map(dashboardCard).join('');const c=d.counts||{};$('centralSummary').innerHTML=`<strong>Gesamtstatus: ${dashboardStateLabel(d.overall)}</strong> · ${c.ok||0} bereit · ${c.warn||0} prüfen · ${c.error||0} Fehler · ${c.disabled||0} aus · geprüft ${new Date((d.checked_at||0)*1000).toLocaleTimeString('de-DE')}`;}catch(e){$('centralSummary').textContent=e.message;notice(e.message,false)}}
async function loadCentralDiagnostics(){try{$('centralDiagnostics').textContent='Diagnose läuft …';const d=await api('/_internal/dashboard/diagnostics');renderResourceCards(d);$('centralDiagnostics').textContent=JSON.stringify(d,null,2);$('centralCards').innerHTML=(d.items||[]).map(dashboardCard).join('');notice(d.overall==='error'?'Diagnose abgeschlossen: Fehler gefunden.':'Diagnose abgeschlossen.',d.overall!=='error')}catch(e){$('centralDiagnostics').textContent=e.message;notice(e.message,false)}}
function startCentralDashboardRefresh(){if(centralDashboardTimer)clearInterval(centralDashboardTimer);loadCentralDashboard();centralDashboardTimer=setInterval(()=>{if($('systemOverview')&&$('systemOverview').classList.contains('active'))loadCentralDashboard()},15000)}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'systemOverview\',this)">Übersicht</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='systemOverview')startCentralDashboardRefresh();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
