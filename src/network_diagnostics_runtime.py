#!/usr/bin/env python3
"""Robuster Internet-Speedtest und LTE-Diagnose für PowerGateway."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

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


def _json_from_output(text: str) -> dict[str, Any] | None:
    value = (text or '').strip().lstrip('\ufeff')
    if not value:
        return None
    for candidate in (value, value[value.find('{'):value.rfind('}') + 1] if '{' in value and '}' in value else ''):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _history() -> list[dict[str, Any]]:
    try:
        value = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, list) else []
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def _store(entry: dict[str, Any]) -> None:
    rows = _history()
    rows.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(rows[-50:], ensure_ascii=False, indent=2), encoding='utf-8')


def _cli_entry(raw: dict[str, Any], started: float) -> dict[str, Any]:
    return {
        'ok': True,
        'tool': 'speedtest-cli',
        'timestamp': int(time.time()),
        'download_mbps': round(float(raw.get('download', 0)) / 1_000_000, 2),
        'upload_mbps': round(float(raw.get('upload', 0)) / 1_000_000, 2),
        'ping_ms': round(float(raw.get('ping', 0)), 2),
        'server': (raw.get('server') or {}).get('sponsor') or (raw.get('server') or {}).get('name'),
        'isp': (raw.get('client') or {}).get('isp'),
        'elapsed_seconds': round(time.monotonic() - started, 1),
    }


def _ookla_entry(raw: dict[str, Any], started: float) -> dict[str, Any]:
    return {
        'ok': True,
        'tool': 'ookla-speedtest',
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


def _attempt_speedtest(executable: str, commands: list[list[str]], parser: Callable[[dict[str, Any], float], dict[str, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    failures: list[dict[str, Any]] = []
    for command in commands:
        result = _run(command, 180)
        raw = _json_from_output(result.stdout)
        if result.returncode == 0 and raw is not None:
            try:
                entry = parser(raw, started)
                _store(entry)
                return entry
            except (TypeError, ValueError, KeyError) as exc:
                failures.append({'command': command, 'message': str(exc), 'stdout': result.stdout[:800]})
                continue
        failures.append({
            'command': command,
            'returncode': result.returncode,
            'stdout': (result.stdout or '').strip()[:800],
            'stderr': (result.stderr or '').strip()[:800],
        })
    return {'ok': False, 'tool': Path(executable).name, 'attempts': failures}


def run_speedtest() -> dict[str, Any]:
    # Debian speedtest-cli installiert teilweise auch /usr/bin/speedtest. Deshalb
    # wird die eindeutige speedtest-cli-Datei zuerst verwendet.
    cli = shutil.which('speedtest-cli')
    if cli:
        result = _attempt_speedtest(cli, [[cli, '--json', '--secure'], [cli, '--json']], _cli_entry)
        if result.get('ok'):
            return result
    else:
        result = {'ok': False, 'attempts': []}

    generic = shutil.which('speedtest')
    if generic and generic != cli:
        version = _run([generic, '--version'], 10)
        version_text = f'{version.stdout}\n{version.stderr}'.lower()
        is_python_cli = 'speedtest-cli' in version_text or 'sivel' in version_text
        if is_python_cli:
            second = _attempt_speedtest(generic, [[generic, '--json', '--secure'], [generic, '--json']], _cli_entry)
        else:
            second = _attempt_speedtest(generic, [
                [generic, '--accept-license', '--accept-gdpr', '-f', 'json'],
                [generic, '--accept-license', '--accept-gdpr', '--format=json'],
                [generic, '-f', 'json'],
            ], _ookla_entry)
        if second.get('ok'):
            return second
        result.setdefault('fallback_attempts', []).append(second)

    if not cli and not generic:
        return {'ok': False, 'message': 'Speedtest-Werkzeug fehlt.', 'install_hint': 'sudo apt install speedtest-cli'}
    result['message'] = 'Das installierte Speedtest-Werkzeug konnte keine gültige JSON-Messung liefern.'
    result['diagnostic_commands'] = ['speedtest-cli --version', 'speedtest-cli --json --secure', 'speedtest --version']
    return result


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


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {'', '--', 'null', 'None'}


def _number(value: Any) -> float | None:
    if not _present(value):
        return None
    match = re.search(r'-?\d+(?:\.\d+)?', str(value))
    return float(match.group(0)) if match else None


def _quality(rsrp: float | None, percent: float | None) -> str:
    if rsrp is not None:
        return 'hervorragend' if rsrp >= -85 else 'gut' if rsrp >= -95 else 'ausreichend' if rsrp >= -105 else 'schlecht' if rsrp >= -115 else 'kritisch'
    if percent is not None:
        return 'hervorragend' if percent >= 80 else 'gut' if percent >= 60 else 'ausreichend' if percent >= 40 else 'schlecht' if percent >= 20 else 'kritisch'
    return 'unbekannt'


def _modemmanager() -> dict[str, Any] | None:
    listing = _run(['mmcli', '-L'], 8)
    match = re.search(r'/Modem/(\d+)', listing.stdout)
    if not match:
        return None
    modem = match.group(1)
    _run(['mmcli', '-m', modem, '--signal-setup=10'], 10)
    signal_result = _run(['mmcli', '-m', modem, '--signal-get', '-J'], 12)
    modem_result = _run(['mmcli', '-m', modem, '-J'], 12)
    signal_raw = _json_from_output(signal_result.stdout) or {}
    modem_raw = _json_from_output(modem_result.stdout) or {}
    signal = ((signal_raw.get('modem') or {}).get('signal') or {})
    lte = signal.get('lte') or {}
    if not any(_present(v) for v in lte.values()):
        return None
    rsrp = _number(lte.get('rsrp'))
    generic = modem_raw.get('modem') or {}
    return {
        'ok': True,
        'source': 'ModemManager',
        'firmware_api': 'mmcli',
        'modem': modem,
        'quality': _quality(rsrp, None),
        'rsrp': lte.get('rsrp'),
        'rsrq': lte.get('rsrq'),
        'sinr': lte.get('snr'),
        'rssi': lte.get('rssi'),
        'raw': {'signal': signal, 'modem': generic},
    }


def _zte_get(gateway: str, commands: list[str]) -> tuple[dict[str, Any] | None, str]:
    query = urllib.parse.urlencode({'isTest': 'false', 'cmd': ','.join(commands), 'multi_data': '1'})
    url = f'http://{gateway}/goform/goform_get_cmd_process?{query}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PowerGateway/0.9'})
        with urllib.request.urlopen(request, timeout=8) as response:
            return _json_from_output(response.read().decode('utf-8', errors='replace')), url
    except (OSError, ValueError):
        return None, url


def _zte(interface: str = 'eth1') -> dict[str, Any] | None:
    gateway = _gateway(interface)
    if not gateway:
        return None
    sets = [
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'rsrp', 'rsrq', 'snr', 'lte_rsrp', 'lte_rsrq', 'lte_snr', 'cell_id', 'lte_band'],
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'lte_rsrp', 'lte_rsrq', 'lte_snr', 'cell_id', 'lte_band', 'imei', 'imsi', 'sim_status', 'modem_main_state'],
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'cell_id', 'lac_code', 'wan_lte_ca', 'lte_band', 'rmcc', 'rmnc', 'simcard_roam'],
    ]
    merged: dict[str, Any] = {}
    urls: list[str] = []
    for commands in sets:
        raw, url = _zte_get(gateway, commands)
        urls.append(url)
        if raw:
            for key, value in raw.items():
                if _present(value) or key not in merged:
                    merged[key] = value
    if not merged:
        return None

    bars = _number(merged.get('signalbar'))
    percent = bars * 20 if bars is not None and bars <= 5 else bars
    rsrp = _number(merged.get('lte_rsrp'))
    if rsrp is None:
        rsrp = _number(merged.get('rsrp'))
    result = {
        'source': 'ZTE-Webschnittstelle',
        'firmware_api': 'goform_get_cmd_process',
        'interface': interface,
        'gateway': gateway,
        'provider': merged.get('network_provider') or '',
        'network_type': merged.get('network_type') or '',
        'signal_percent': percent,
        'rssi': merged.get('rssi') or '',
        'rsrp': rsrp if rsrp is not None else '',
        'rsrq': merged.get('lte_rsrq') or merged.get('rsrq') or '',
        'sinr': merged.get('lte_snr') or merged.get('snr') or '',
        'cell_id': merged.get('cell_id') or '',
        'band': merged.get('lte_band') or merged.get('wan_lte_ca') or '',
        'imei': merged.get('imei') or '',
        'sim_status': merged.get('sim_status') or merged.get('modem_main_state') or '',
        'quality': _quality(rsrp, percent),
        'raw': merged,
        'attempted_endpoints': urls,
    }
    useful = any(_present(result.get(key)) for key in ('provider', 'network_type', 'rssi', 'rsrp', 'rsrq', 'sinr', 'cell_id', 'band')) or percent is not None
    if useful:
        result['ok'] = True
    else:
        result.update({
            'ok': False,
            'message': 'Die ZTE-Webschnittstelle ist erreichbar, aber die Geräte-Firmware liefert über die bekannten Parameter keine Empfangswerte.',
            'firmware_hint': 'Für diese Firmware muss der konkrete Netzwerkaufruf der ZTE-Weboberfläche ermittelt werden.',
        })
    return result


def lte_signal() -> dict[str, Any]:
    return _modemmanager() or _zte('eth1') or {
        'ok': False,
        'message': 'Keine unterstützte LTE-Signalschnittstelle gefunden.',
        'interface': 'eth1',
        'gateway': _gateway('eth1'),
    }


@app.post('/_internal/network/speedtest')
@legacy.login_required
def robust_speedtest_route() -> Response:
    return jsonify(run_speedtest())


@app.get('/_internal/network/speedtest/history')
@legacy.login_required
def robust_speedtest_history_route() -> Response:
    return jsonify({'items': list(reversed(_history()))})


@app.get('/_internal/network/lte-signal')
@legacy.login_required
def robust_lte_signal_route() -> Response:
    return jsonify(lte_signal())


SECTION = r'''
<div class="section"><div class="toolbar"><div><h3>Internet-Speedtest</h3><div class="muted">Misst Download, Upload und Reaktionszeit. Ein Test kann merklich LTE-Datenvolumen verbrauchen.</div></div><button onclick="runNetworkSpeedtest()">Speedtest starten</button></div><pre id="speedtestResult">Noch kein Test ausgeführt.</pre><details><summary>Letzte Messungen</summary><pre id="speedtestHistory">Noch nicht geladen.</pre></details></div>
<div class="section"><div class="toolbar"><div><h3>LTE-Empfang</h3><div class="muted">Liest Signalqualität und Geräteinformationen über ModemManager oder unterstützte ZTE-Firmware-Schnittstellen.</div></div><button onclick="loadLteSignal()">Empfang prüfen</button></div><pre id="lteSignalResult">Noch nicht geprüft.</pre></div>
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
