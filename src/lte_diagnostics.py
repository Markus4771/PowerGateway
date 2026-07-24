#!/usr/bin/env python3
"""Internet-Speedtest und LTE-Empfangsdiagnose für PowerGateway."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from flask import Response, jsonify

import webapp_features as features

app = features.app
legacy = features.legacy
runtime = features.runtime
DATA_DIR = Path('/var/lib/powergateway')
HISTORY_FILE = DATA_DIR / 'speedtest_history.json'


def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout='', stderr=str(exc))


def _gateway(interface: str = 'eth1') -> str | None:
    result = _run(['/usr/sbin/ip', '-4', 'route', 'show', 'dev', interface], 5)
    match = re.search(r'\bdefault via ([0-9.]+)', result.stdout)
    if match:
        return match.group(1)
    result = _run(['/usr/sbin/ip', '-4', 'route', 'show', 'default'], 5)
    for line in result.stdout.splitlines():
        if f' dev {interface}' in line:
            match = re.search(r'\bvia ([0-9.]+)', line)
            if match:
                return match.group(1)
    return None


def _load_history() -> list[dict[str, Any]]:
    try:
        value = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, list) else []
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def _save_history(entries: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries[-50:], ensure_ascii=False, indent=2), encoding='utf-8')


def run_speedtest() -> dict[str, Any]:
    executable = shutil.which('speedtest') or shutil.which('speedtest-cli')
    if not executable:
        return {
            'ok': False,
            'message': 'Speedtest-Werkzeug fehlt. Bitte Paket speedtest-cli installieren.',
            'install_hint': 'sudo apt install speedtest-cli',
        }
    started = time.monotonic()
    if executable.endswith('speedtest-cli'):
        result = _run([executable, '--json', '--secure'], 120)
        if result.returncode != 0:
            return {'ok': False, 'message': result.stderr.strip() or result.stdout.strip() or 'Speedtest fehlgeschlagen'}
        try:
            raw = json.loads(result.stdout)
            entry = {
                'ok': True,
                'timestamp': int(time.time()),
                'download_mbps': round(float(raw.get('download', 0)) / 1_000_000, 2),
                'upload_mbps': round(float(raw.get('upload', 0)) / 1_000_000, 2),
                'ping_ms': round(float(raw.get('ping', 0)), 2),
                'server': (raw.get('server') or {}).get('sponsor') or (raw.get('server') or {}).get('name'),
                'elapsed_seconds': round(time.monotonic() - started, 1),
            }
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return {'ok': False, 'message': f'Ungültige Speedtest-Ausgabe: {exc}'}
    else:
        result = _run([executable, '--accept-license', '--accept-gdpr', '-f', 'json'], 120)
        if result.returncode != 0:
            return {'ok': False, 'message': result.stderr.strip() or result.stdout.strip() or 'Speedtest fehlgeschlagen'}
        try:
            raw = json.loads(result.stdout)
            entry = {
                'ok': True,
                'timestamp': int(time.time()),
                'download_mbps': round(float((raw.get('download') or {}).get('bandwidth', 0)) * 8 / 1_000_000, 2),
                'upload_mbps': round(float((raw.get('upload') or {}).get('bandwidth', 0)) * 8 / 1_000_000, 2),
                'ping_ms': round(float((raw.get('ping') or {}).get('latency', 0)), 2),
                'jitter_ms': round(float((raw.get('ping') or {}).get('jitter', 0)), 2),
                'packet_loss_percent': raw.get('packetLoss'),
                'server': (raw.get('server') or {}).get('name'),
                'isp': raw.get('isp'),
                'elapsed_seconds': round(time.monotonic() - started, 1),
            }
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return {'ok': False, 'message': f'Ungültige Speedtest-Ausgabe: {exc}'}
    history = _load_history()
    history.append(entry)
    _save_history(history)
    return entry


def _quality(rsrp: float | None = None, percent: float | None = None) -> str:
    if rsrp is not None:
        return 'hervorragend' if rsrp >= -85 else 'gut' if rsrp >= -95 else 'ausreichend' if rsrp >= -105 else 'schlecht' if rsrp >= -115 else 'kritisch'
    if percent is not None:
        return 'hervorragend' if percent >= 80 else 'gut' if percent >= 60 else 'ausreichend' if percent >= 40 else 'schlecht' if percent >= 20 else 'kritisch'
    return 'unbekannt'


def _modemmanager_signal() -> dict[str, Any] | None:
    listing = _run(['mmcli', '-L'], 8)
    match = re.search(r'/Modem/(\d+)', listing.stdout)
    if not match:
        return None
    modem = match.group(1)
    _run(['mmcli', '-m', modem, '--signal-setup=10'], 10)
    result = _run(['mmcli', '-m', modem, '--signal-get', '-J'], 12)
    if result.returncode != 0:
        return None
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    signal = ((raw.get('modem') or {}).get('signal') or {})
    lte = signal.get('lte') or {}
    rsrp = lte.get('rsrp')
    return {'source': 'ModemManager', 'modem': modem, 'lte': lte, 'quality': _quality(float(rsrp) if rsrp is not None else None)}


def _zte_web_signal(interface: str = 'eth1') -> dict[str, Any] | None:
    gateway = _gateway(interface)
    if not gateway:
        return None
    commands = 'signalbar,network_type,network_provider,rssi,rsrp,rsrq,snr,lte_rsrp,lte_rsrq,lte_snr,cell_id,lte_band'
    query = urllib.parse.urlencode({'isTest': 'false', 'cmd': commands, 'multi_data': '1'})
    url = f'http://{gateway}/goform/goform_get_cmd_process?{query}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'PowerGateway/0.9'})
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = json.loads(response.read().decode('utf-8', errors='replace'))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    percent = None
    try:
        bars = float(raw.get('signalbar'))
        percent = bars * 20 if bars <= 5 else bars
    except (TypeError, ValueError):
        pass
    rsrp = None
    for key in ('lte_rsrp', 'rsrp'):
        try:
            rsrp = float(str(raw.get(key)).replace('dBm', '').strip())
            break
        except (TypeError, ValueError):
            continue
    return {
        'source': 'ZTE-Webschnittstelle',
        'interface': interface,
        'gateway': gateway,
        'provider': raw.get('network_provider'),
        'network_type': raw.get('network_type'),
        'signal_percent': percent,
        'rssi': raw.get('rssi'),
        'rsrp': rsrp if rsrp is not None else raw.get('rsrp') or raw.get('lte_rsrp'),
        'rsrq': raw.get('rsrq') or raw.get('lte_rsrq'),
        'sinr': raw.get('snr') or raw.get('lte_snr'),
        'cell_id': raw.get('cell_id'),
        'band': raw.get('lte_band'),
        'quality': _quality(rsrp, percent),
        'raw': raw,
    }


def lte_signal() -> dict[str, Any]:
    result = _modemmanager_signal()
    if result:
        return {'ok': True, **result}
    result = _zte_web_signal('eth1')
    if result:
        return {'ok': True, **result}
    return {
        'ok': False,
        'message': 'LTE-Stick erkannt, aber Empfangswerte sind über ModemManager oder die ZTE-Webschnittstelle nicht verfügbar.',
        'interface': 'eth1',
        'gateway': _gateway('eth1'),
    }


@app.post('/_internal/network/speedtest')
@legacy.login_required
def speedtest_route() -> Response:
    return jsonify(run_speedtest())


@app.get('/_internal/network/speedtest/history')
@legacy.login_required
def speedtest_history_route() -> Response:
    return jsonify({'items': list(reversed(_load_history()))})


@app.get('/_internal/network/lte-signal')
@legacy.login_required
def lte_signal_route() -> Response:
    return jsonify(lte_signal())


SECTION = r'''
<div class="section"><div class="toolbar"><div><h3>Internet-Speedtest</h3><div class="muted">Misst Download, Upload und Reaktionszeit. Ein Test kann merklich LTE-Datenvolumen verbrauchen.</div></div><button onclick="runNetworkSpeedtest()">Speedtest starten</button></div><pre id="speedtestResult">Noch kein Test ausgeführt.</pre><details><summary>Letzte Messungen</summary><pre id="speedtestHistory">Noch nicht geladen.</pre></details></div>
<div class="section"><div class="toolbar"><div><h3>LTE-Empfang</h3><div class="muted">Liest Signalqualität, Provider, Netztyp und Funkwerte aus, soweit der USB-Stick sie bereitstellt.</div></div><button onclick="loadLteSignal()">Empfang prüfen</button></div><pre id="lteSignalResult">Noch nicht geprüft.</pre></div>
'''
JS = r'''
async function runNetworkSpeedtest(){try{$('speedtestResult').textContent='Speedtest läuft. Dies kann etwa eine Minute dauern …';const d=await api('/_internal/network/speedtest',{method:'POST'});$('speedtestResult').textContent=JSON.stringify(d,null,2);notice(d.ok?'Speedtest abgeschlossen.':(d.message||'Speedtest fehlgeschlagen.'),!!d.ok);loadSpeedtestHistory()}catch(e){$('speedtestResult').textContent=e.message;notice(e.message,false)}}
async function loadSpeedtestHistory(){try{const d=await api('/_internal/network/speedtest/history');$('speedtestHistory').textContent=JSON.stringify(d.items||[],null,2)}catch(e){$('speedtestHistory').textContent=e.message}}
async function loadLteSignal(){try{$('lteSignalResult').textContent='LTE-Empfang wird geprüft …';const d=await api('/_internal/network/lte-signal');$('lteSignalResult').textContent=JSON.stringify(d,null,2);notice(d.ok?`LTE-Empfang: ${d.quality||'ermittelt'}`:(d.message||'Keine Empfangswerte verfügbar.'),!!d.ok)}catch(e){$('lteSignalResult').textContent=e.message;notice(e.message,false)}}
'''
page = runtime.PAGE
page = page.replace('<div class="section"><h3>Gesamtdiagnose</h3>', SECTION + '<div class="section"><h3>Gesamtdiagnose</h3>')
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
