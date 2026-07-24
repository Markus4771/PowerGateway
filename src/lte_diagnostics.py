#!/usr/bin/env python3
"""Internet-Speedtest und professionelle LTE-Diagnose für PowerGateway."""
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
SPEEDTEST_HISTORY_FILE = DATA_DIR / 'speedtest_history.json'
LTE_HISTORY_FILE = DATA_DIR / 'lte_signal_history.json'


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


def _read_history(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, list) else []
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def _append_history(path: Path, entry: dict[str, Any], limit: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history = _read_history(path)
    history.append(entry)
    path.write_text(json.dumps(history[-limit:], ensure_ascii=False, indent=2), encoding='utf-8')


def _extract_json(text: str) -> dict[str, Any] | None:
    value = (text or '').strip().lstrip('\ufeff')
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = value.find('{'), value.rfind('}')
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _parse_speedtest_cli(raw: dict[str, Any], started: float) -> dict[str, Any]:
    return {
        'ok': True,
        'timestamp': int(time.time()),
        'download_mbps': round(float(raw.get('download', 0)) / 1_000_000, 2),
        'upload_mbps': round(float(raw.get('upload', 0)) / 1_000_000, 2),
        'ping_ms': round(float(raw.get('ping', 0)), 2),
        'server': (raw.get('server') or {}).get('sponsor') or (raw.get('server') or {}).get('name'),
        'server_location': (raw.get('server') or {}).get('name'),
        'isp': (raw.get('client') or {}).get('isp'),
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
        'server_location': (raw.get('server') or {}).get('location'),
        'isp': raw.get('isp'),
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'tool': 'ookla-speedtest',
    }


def run_speedtest() -> dict[str, Any]:
    executable = shutil.which('speedtest-cli') or shutil.which('speedtest')
    if not executable:
        return {'ok': False, 'message': 'Speedtest-Werkzeug fehlt.', 'install_hint': 'sudo apt install speedtest-cli'}
    started = time.monotonic()
    basename = Path(executable).name
    if basename == 'speedtest-cli':
        attempts = [[executable, '--json', '--secure'], [executable, '--json']]
        parser = _parse_speedtest_cli
    else:
        attempts = [[executable, '--accept-license', '--accept-gdpr', '-f', 'json'], [executable, '-f', 'json']]
        parser = _parse_ookla
    failures: list[dict[str, Any]] = []
    for command in attempts:
        result = _run(command, 180)
        raw = _extract_json(result.stdout)
        if result.returncode == 0 and raw:
            try:
                entry = parser(raw, started)
            except (ValueError, TypeError, KeyError) as exc:
                failures.append({'command': command, 'message': str(exc), 'stdout_preview': result.stdout[:1000]})
                continue
            _append_history(SPEEDTEST_HISTORY_FILE, entry, 50)
            return entry
        failures.append({
            'command': command,
            'returncode': result.returncode,
            'stdout_preview': (result.stdout or '')[:1000],
            'stderr_preview': (result.stderr or '')[:1000],
        })
    return {'ok': False, 'message': 'Speedtest konnte nicht ausgeführt werden.', 'tool': basename, 'attempts': failures}


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() not in {'', '--', 'null', 'None', 'unknown'}


def _number(value: Any) -> float | None:
    if not _nonempty(value):
        return None
    match = re.search(r'-?\d+(?:\.\d+)?', str(value))
    return float(match.group(0)) if match else None


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
    signal_result = _run(['mmcli', '-m', modem, '--signal-get', '-J'], 12)
    modem_result = _run(['mmcli', '-m', modem, '-J'], 12)
    signal_raw = _extract_json(signal_result.stdout) or {}
    modem_raw = _extract_json(modem_result.stdout) or {}
    signal = ((signal_raw.get('modem') or {}).get('signal') or {})
    lte = signal.get('lte') or {}
    if not any(_nonempty(v) for v in lte.values()):
        return None
    generic = (modem_raw.get('modem') or {}).get('generic') or {}
    rsrp = _number(lte.get('rsrp'))
    return {
        'ok': True, 'source': 'ModemManager', 'firmware_api': 'mmcli', 'modem': modem,
        'provider': generic.get('operator-name') or '', 'network_type': generic.get('access-technologies') or 'LTE',
        'signal_percent': _number(generic.get('signal-quality')), 'rssi': lte.get('rssi') or '',
        'rsrp': rsrp if rsrp is not None else '', 'rsrq': lte.get('rsrq') or '', 'sinr': lte.get('snr') or '',
        'band': '', 'cell_id': '', 'quality': _quality(rsrp), 'imei': generic.get('equipment-identifier') or '',
        'sim_status': generic.get('state') or '', 'raw': {'signal': signal, 'modem': modem_raw},
    }


def _zte_request(gateway: str, commands: list[str]) -> tuple[dict[str, Any] | None, str, str]:
    query = urllib.parse.urlencode({'isTest': 'false', 'cmd': ','.join(commands), 'multi_data': '1'})
    url = f'http://{gateway}/goform/goform_get_cmd_process?{query}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PowerGateway/0.9'})
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read().decode('utf-8', errors='replace')
        return _extract_json(body), url, body[:1000]
    except (OSError, ValueError) as exc:
        return None, url, str(exc)


def _zte_web_signal(interface: str = 'eth1', full_analysis: bool = False) -> dict[str, Any] | None:
    gateway = _gateway(interface)
    if not gateway:
        return None
    command_sets = [
        ['signalbar','network_type','network_provider','rssi','rsrp','rsrq','snr','lte_rsrp','lte_rsrq','lte_snr','cell_id','lte_band'],
        ['modem_main_state','pin_status','sim_status','simcard_roam','network_type','network_provider','rmcc','rmnc','signalbar','cell_id','lte_band'],
        ['dev_name','imei','imsi','iccid','wa_inner_version','cr_version','hardware_version','web_version'],
        ['wan_ipaddr','ipv6_wan_ipaddr','dns_mode','prefer_dns_manual','standby_dns_manual','monthly_tx_bytes','monthly_rx_bytes'],
        ['lac_code','wan_lte_ca','lte_pci','lte_earfcn','lte_rssi','lte_rsrp','lte_rsrq','lte_snr'],
    ]
    merged: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    for commands in command_sets:
        raw, url, preview = _zte_request(gateway, commands)
        attempts.append({'commands': commands, 'url': url, 'response_preview': preview})
        if raw:
            for key, value in raw.items():
                if _nonempty(value) or key not in merged:
                    merged[key] = value
    if not merged:
        return None
    signalbar = _number(merged.get('signalbar'))
    percent = signalbar * 20 if signalbar is not None and signalbar <= 5 else signalbar
    rsrp = _number(merged.get('lte_rsrp')) or _number(merged.get('rsrp'))
    rsrq = merged.get('lte_rsrq') or merged.get('rsrq') or ''
    sinr = merged.get('lte_snr') or merged.get('snr') or ''
    provider = merged.get('network_provider') or ''
    network_type = merged.get('network_type') or ''
    cell_id = merged.get('cell_id') or ''
    band = merged.get('lte_band') or merged.get('wan_lte_ca') or ''
    useful = any(_nonempty(v) for v in (signalbar, rsrp, rsrq, sinr, provider, network_type, cell_id, band, merged.get('rssi')))
    result: dict[str, Any] = {
        'ok': useful, 'source': 'ZTE-Webschnittstelle', 'firmware_api': 'goform_get_cmd_process',
        'interface': interface, 'gateway': gateway, 'provider': provider, 'network_type': network_type,
        'signal_percent': percent, 'rssi': merged.get('rssi') or merged.get('lte_rssi') or '',
        'rsrp': rsrp if rsrp is not None else '', 'rsrq': rsrq, 'sinr': sinr,
        'cell_id': cell_id, 'band': band, 'quality': _quality(rsrp, percent),
        'sim_status': merged.get('sim_status') or merged.get('pin_status') or merged.get('modem_main_state') or '',
        'roaming': merged.get('simcard_roam') or '', 'imei': merged.get('imei') or '',
        'imsi_available': bool(_nonempty(merged.get('imsi'))), 'iccid_available': bool(_nonempty(merged.get('iccid'))),
        'device_name': merged.get('dev_name') or '', 'firmware_version': merged.get('wa_inner_version') or merged.get('cr_version') or '',
        'hardware_version': merged.get('hardware_version') or '', 'public_ipv4': merged.get('wan_ipaddr') or '',
        'public_ipv6': merged.get('ipv6_wan_ipaddr') or '', 'raw': merged,
    }
    if full_analysis:
        result['attempts'] = attempts
    if not useful:
        result['message'] = 'Die ZTE-Webschnittstelle ist erreichbar, liefert über die bekannten Parameter jedoch keine Funkwerte.'
    return result


def lte_signal(full_analysis: bool = False) -> dict[str, Any]:
    result = _modemmanager_signal() or _zte_web_signal('eth1', full_analysis)
    if not result:
        return {'ok': False, 'message': 'Keine LTE-Empfangswerte verfügbar.', 'interface': 'eth1', 'gateway': _gateway('eth1')}
    if result.get('ok'):
        history_entry = {k: result.get(k) for k in ('provider','network_type','signal_percent','rssi','rsrp','rsrq','sinr','band','cell_id','quality')}
        history_entry['timestamp'] = int(time.time())
        _append_history(LTE_HISTORY_FILE, history_entry, 500)
    return result


@app.post('/_internal/network/speedtest')
@legacy.login_required
def speedtest_route() -> Response:
    return jsonify(run_speedtest())


@app.get('/_internal/network/speedtest/history')
@legacy.login_required
def speedtest_history_route() -> Response:
    return jsonify({'items': list(reversed(_read_history(SPEEDTEST_HISTORY_FILE)))})


@app.get('/_internal/network/lte-signal')
@legacy.login_required
def lte_signal_route() -> Response:
    return jsonify(lte_signal(False))


@app.get('/_internal/network/lte-signal/history')
@legacy.login_required
def lte_history_route() -> Response:
    return jsonify({'items': list(reversed(_read_history(LTE_HISTORY_FILE)[-100:]))})


@app.get('/_internal/network/lte-analyze')
@legacy.login_required
def lte_analyze_route() -> Response:
    return jsonify(lte_signal(True))


SECTION = r'''
<div class="section"><div class="toolbar"><div><h3>Internet-Speedtest</h3><div class="muted">Misst Download, Upload und Reaktionszeit. Ein Test kann merklich LTE-Datenvolumen verbrauchen.</div></div><button onclick="runNetworkSpeedtest()">Speedtest starten</button></div><div id="speedtestCards" class="grid"><div class="card"><div class="muted">Noch kein Test ausgeführt.</div></div></div><details class="section"><summary>Letzte Messungen</summary><div id="speedtestHistory" class="section muted">Noch nicht geladen.</div></details><details><summary>Technische Rohdaten</summary><pre id="speedtestRaw">Noch kein Test ausgeführt.</pre></details></div>
<div class="section"><div class="toolbar"><div><h3>LTE Professional</h3><div class="muted">Zeigt alle Empfangs-, Netz-, SIM- und Gerätewerte, die der Stick tatsächlich bereitstellt.</div></div><div><button class="secondary" onclick="analyzeLte()">LTE vollständig analysieren</button> <button onclick="loadLteSignal()">Empfang prüfen</button></div></div><div id="lteStatus" class="muted">Noch nicht geprüft.</div><div id="lteCards" class="grid section"></div><div class="card section"><h3>Funkwerte</h3><div id="lteRadioTable"></div></div><details class="section"><summary>LTE-Verlauf</summary><div id="lteHistory" class="section muted">Noch nicht geladen.</div></details><details><summary>Technische Rohdaten</summary><pre id="lteSignalRaw">Noch nicht geprüft.</pre></details></div>
'''

JS = r'''
function metricCard(label,value,unit=''){return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${esc(value??'nicht verfügbar')}${value!==null&&value!==undefined&&value!==''&&unit?' '+esc(unit):''}</div></div>`}
function displayValue(v){return v===null||v===undefined||v===''?'nicht verfügbar':v}
function renderSpeedtest(d){$('speedtestRaw').textContent=JSON.stringify(d,null,2);if(!d.ok){$('speedtestCards').innerHTML=metricCard('Fehler',d.message||'Speedtest fehlgeschlagen');return}$('speedtestCards').innerHTML=[metricCard('Download',d.download_mbps,'Mbit/s'),metricCard('Upload',d.upload_mbps,'Mbit/s'),metricCard('Ping',d.ping_ms,'ms'),metricCard('Provider',d.isp),metricCard('Testserver',d.server),metricCard('Dauer',d.elapsed_seconds,'s')].join('')}
async function runNetworkSpeedtest(){try{$('speedtestCards').innerHTML=metricCard('Status','Speedtest läuft …');const d=await api('/_internal/network/speedtest',{method:'POST'});renderSpeedtest(d);notice(d.ok?'Speedtest abgeschlossen.':(d.message||'Speedtest fehlgeschlagen.'),!!d.ok);loadSpeedtestHistory()}catch(e){$('speedtestCards').innerHTML=metricCard('Fehler',e.message);notice(e.message,false)}}
async function loadSpeedtestHistory(){try{const d=await api('/_internal/network/speedtest/history');const items=d.items||[];$('speedtestHistory').innerHTML=items.length?items.slice(0,20).map(x=>`<div class="status-row"><span>${new Date((x.timestamp||0)*1000).toLocaleString('de-DE')}</span><strong>${esc(x.download_mbps)} ↓ / ${esc(x.upload_mbps)} ↑ Mbit/s · ${esc(x.ping_ms)} ms</strong></div>`).join(''):'Noch keine Messungen.'}catch(e){$('speedtestHistory').textContent=e.message}}
function renderLte(d){$('lteSignalRaw').textContent=JSON.stringify(d,null,2);$('lteStatus').innerHTML=d.ok?`<strong>Empfang: ${esc(d.quality||'ermittelt')}</strong> · Quelle: ${esc(d.source||'unbekannt')}`:`<strong>Keine Funkwerte:</strong> ${esc(d.message||'nicht verfügbar')}`;$('lteCards').innerHTML=[metricCard('Signal',d.signal_percent,'%'),metricCard('Qualität',d.quality),metricCard('Netztyp',d.network_type),metricCard('Provider',d.provider),metricCard('LTE-Band',d.band),metricCard('Cell-ID',d.cell_id),metricCard('SIM-Status',d.sim_status),metricCard('Firmware',d.firmware_version),metricCard('Gateway',d.gateway),metricCard('Öffentliche IPv4',d.public_ipv4)].join('');const rows=[['RSSI',d.rssi,'dBm'],['RSRP',d.rsrp,'dBm'],['RSRQ',d.rsrq,'dB'],['SINR/SNR',d.sinr,'dB'],['Roaming',d.roaming,''],['Gerät',d.device_name,''],['Hardware',d.hardware_version,''],['IMEI',d.imei?'vorhanden':'nicht verfügbar','']];$('lteRadioTable').innerHTML='<table><thead><tr><th>Parameter</th><th>Wert</th><th>Einheit</th></tr></thead><tbody>'+rows.map(r=>`<tr><td>${esc(r[0])}</td><td>${esc(displayValue(r[1]))}</td><td>${esc(r[2])}</td></tr>`).join('')+'</tbody></table>'}
async function loadLteSignal(){try{$('lteStatus').textContent='LTE-Empfang wird geprüft …';const d=await api('/_internal/network/lte-signal');renderLte(d);notice(d.ok?`LTE-Empfang: ${d.quality||'ermittelt'}`:(d.message||'Keine Empfangswerte verfügbar.'),!!d.ok);loadLteHistory()}catch(e){$('lteStatus').textContent=e.message;notice(e.message,false)}}
async function analyzeLte(){try{$('lteStatus').textContent='Vollständige LTE-Analyse läuft …';const d=await api('/_internal/network/lte-analyze');renderLte(d);notice(d.ok?'LTE-Analyse abgeschlossen.':'LTE-Analyse abgeschlossen, keine Funkwerte gefunden.',!!d.ok)}catch(e){$('lteStatus').textContent=e.message;notice(e.message,false)}}
async function loadLteHistory(){try{const d=await api('/_internal/network/lte-signal/history');const items=d.items||[];$('lteHistory').innerHTML=items.length?items.slice(0,30).map(x=>`<div class="status-row"><span>${new Date((x.timestamp||0)*1000).toLocaleString('de-DE')}</span><strong>${esc(displayValue(x.quality))} · ${esc(displayValue(x.rsrp))} dBm · ${esc(displayValue(x.network_type))}</strong></div>`).join(''):'Noch keine verwertbaren Empfangswerte gespeichert.'}catch(e){$('lteHistory').textContent=e.message}}
'''

page = runtime.PAGE
page = page.replace('<div class="section"><h3>Gesamtdiagnose</h3>', SECTION + '<div class="section"><h3>Gesamtdiagnose</h3>')
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
