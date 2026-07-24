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


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extrahiert JSON auch dann, wenn ein Werkzeug Warnungen davor ausgibt."""
    value = (text or '').strip().lstrip('\ufeff')
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = value.find('{')
    end = value.rfind('}')
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _speedtest_error(result: subprocess.CompletedProcess[str], command: list[str]) -> dict[str, Any]:
    stdout = (result.stdout or '').strip()
    stderr = (result.stderr or '').strip()
    message = stderr or stdout or 'Das Speedtest-Werkzeug lieferte keine Ausgabe.'
    return {
        'ok': False,
        'message': message,
        'returncode': result.returncode,
        'command': command,
        'stdout_preview': stdout[:1000],
        'stderr_preview': stderr[:1000],
    }


def _parse_speedtest_cli(raw: dict[str, Any], started: float) -> dict[str, Any]:
    return {
        'ok': True,
        'timestamp': int(time.time()),
        'download_mbps': round(float(raw.get('download', 0)) / 1_000_000, 2),
        'upload_mbps': round(float(raw.get('upload', 0)) / 1_000_000, 2),
        'ping_ms': round(float(raw.get('ping', 0)), 2),
        'server': (raw.get('server') or {}).get('sponsor') or (raw.get('server') or {}).get('name'),
        'isp': raw.get('client', {}).get('isp') if isinstance(raw.get('client'), dict) else None,
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'tool': 'speedtest-cli',
    }


def _parse_ookla(raw: dict[str, Any], started: float) -> dict[str, Any]:
    return {
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
        'tool': 'ookla-speedtest',
    }


def run_speedtest() -> dict[str, Any]:
    executable = shutil.which('speedtest') or shutil.which('speedtest-cli')
    if not executable:
        return {'ok': False, 'message': 'Speedtest-Werkzeug fehlt.', 'install_hint': 'sudo apt install speedtest-cli'}

    started = time.monotonic()
    basename = Path(executable).name
    attempts: list[list[str]]
    parser = _parse_speedtest_cli
    if basename == 'speedtest-cli':
        attempts = [[executable, '--json', '--secure'], [executable, '--json']]
    else:
        parser = _parse_ookla
        attempts = [
            [executable, '--accept-license', '--accept-gdpr', '-f', 'json'],
            [executable, '--accept-license', '--accept-gdpr', '--format=json'],
            [executable, '-f', 'json'],
        ]

    failures: list[dict[str, Any]] = []
    for command in attempts:
        result = _run(command, 180)
        raw = _extract_json(result.stdout)
        if result.returncode == 0 and raw is not None:
            try:
                entry = parser(raw, started)
            except (ValueError, TypeError, KeyError) as exc:
                failures.append({'command': command, 'message': f'Ausgabe konnte nicht ausgewertet werden: {exc}', 'stdout_preview': result.stdout[:1000]})
                continue
            history = _load_history()
            history.append(entry)
            _save_history(history)
            return entry
        failures.append(_speedtest_error(result, command))

    return {
        'ok': False,
        'message': 'Speedtest konnte mit keiner unterstützten Aufrufvariante ausgeführt werden.',
        'tool': basename,
        'attempts': failures,
        'diagnostic_hint': f'{executable} --version',
    }


def _quality(rsrp: float | None = None, percent: float | None = None) -> str:
    if rsrp is not None:
        return 'hervorragend' if rsrp >= -85 else 'gut' if rsrp >= -95 else 'ausreichend' if rsrp >= -105 else 'schlecht' if rsrp >= -115 else 'kritisch'
    if percent is not None:
        return 'hervorragend' if percent >= 80 else 'gut' if percent >= 60 else 'ausreichend' if percent >= 40 else 'schlecht' if percent >= 20 else 'kritisch'
    return 'unbekannt'


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() not in {'', '--', 'null', 'None'}


def _number(value: Any) -> float | None:
    if not _nonempty(value):
        return None
    match = re.search(r'-?\d+(?:\.\d+)?', str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


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
    raw = _extract_json(result.stdout)
    if not raw:
        return None
    signal = ((raw.get('modem') or {}).get('signal') or {})
    lte = signal.get('lte') or {}
    rsrp = _number(lte.get('rsrp'))
    available = any(_nonempty(value) for value in lte.values())
    if not available:
        return None
    return {'source': 'ModemManager', 'modem': modem, 'lte': lte, 'quality': _quality(rsrp), 'firmware_api': 'mmcli'}


def _zte_request(gateway: str, commands: list[str]) -> tuple[dict[str, Any] | None, str]:
    query = urllib.parse.urlencode({'isTest': 'false', 'cmd': ','.join(commands), 'multi_data': '1'})
    url = f'http://{gateway}/goform/goform_get_cmd_process?{query}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PowerGateway/0.9'})
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read().decode('utf-8', errors='replace')
        return _extract_json(body), url
    except (OSError, ValueError):
        return None, url


def _zte_web_signal(interface: str = 'eth1') -> dict[str, Any] | None:
    gateway = _gateway(interface)
    if not gateway:
        return None

    command_sets = [
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'rsrp', 'rsrq', 'snr', 'lte_rsrp', 'lte_rsrq', 'lte_snr', 'cell_id', 'lte_band'],
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'lte_rsrp', 'lte_rsrq', 'lte_snr', 'cell_id', 'lte_band', 'imei', 'imsi', 'sim_status', 'modem_main_state'],
        ['signalbar', 'network_type', 'network_provider', 'rssi', 'cell_id', 'lac_code', 'wan_lte_ca', 'lte_band', 'rmcc', 'rmnc', 'simcard_roam'],
    ]
    merged: dict[str, Any] = {}
    attempted_urls: list[str] = []
    for commands in command_sets:
        raw, url = _zte_request(gateway, commands)
        attempted_urls.append(url)
        if raw:
            for key, value in raw.items():
                if _nonempty(value) or key not in merged:
                    merged[key] = value

    if not merged:
        return None

    signalbar = _number(merged.get('signalbar'))
    percent = signalbar * 20 if signalbar is not None and signalbar <= 5 else signalbar
    rsrp = _number(merged.get('lte_rsrp')) or _number(merged.get('rsrp'))
    rsrq = merged.get('lte_rsrq') or merged.get('rsrq')
    sinr = merged.get('lte_snr') or merged.get('snr')
    provider = merged.get('network_provider')
    network_type = merged.get('network_type')
    cell_id = merged.get('cell_id')
    band = merged.get('lte_band') or merged.get('wan_lte_ca')

    useful = any(_nonempty(value) for value in (signalbar, rsrp, rsrq, sinr, provider, network_type, cell_id, band, merged.get('rssi')))
    result = {
        'source': 'ZTE-Webschnittstelle',
        'firmware_api': 'goform_get_cmd_process',
        'interface': interface,
        'gateway': gateway,
        'provider': provider or '',
        'network_type': network_type or '',
        'signal_percent': percent,
        'rssi': merged.get('rssi') or '',
        'rsrp': rsrp if rsrp is not None else '',
        'rsrq': rsrq or '',
        'sinr': sinr or '',
        'cell_id': cell_id or '',
        'band': band or '',
        'imei': merged.get('imei') or '',
        'imsi_available': bool(_nonempty(merged.get('imsi'))),
        'sim_status': merged.get('sim_status') or merged.get('modem_main_state') or '',
        'quality': _quality(rsrp, percent),
        'raw': merged,
        'attempted_endpoints': attempted_urls,
    }
    if not useful:
        result.update({
            'ok': False,
            'message': 'Die ZTE-Webschnittstelle ist erreichbar, diese Firmware liefert über die bekannten Goform-Parameter jedoch keine Funkwerte.',
            'firmware_hint': 'Bitte die ZTE-Weboberfläche im Browser öffnen und die Netzwerkaufrufe beim Anzeigen der Signalwerte prüfen.',
        })
    else:
        result['ok'] = True
    return result


def lte_signal() -> dict[str, Any]:
    result = _modemmanager_signal()
    if result:
        return {'ok': True, **result}
    result = _zte_web_signal('eth1')
    if result:
        return result
    return {
        'ok': False,
        'message': 'LTE-Stick erkannt, aber Empfangswerte sind weder über ModemManager noch über die ZTE-Webschnittstelle verfügbar.',
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
<div class="section"><div class="toolbar"><div><h3>LTE-Empfang</h3><div class="muted">Liest Signalqualität, Provider, Netztyp und Funkwerte aus, soweit der USB-Stick und seine Firmware sie bereitstellen.</div></div><button onclick="loadLteSignal()">Empfang prüfen</button></div><pre id="lteSignalResult">Noch nicht geprüft.</pre></div>
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
