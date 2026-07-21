#!/usr/bin/env python3
"""Lokale, schreibgeschützte Status- und Diagnoseoberfläche für PowerGateway.

Die Anwendung stellt keine öffentliche REST-API bereit. Die JSON-Antworten unter
``/_internal`` dienen ausschließlich der lokalen Weboberfläche.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template_string

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA", "/var/lib/powergateway"))
CONFIG_PATH = Path(os.environ.get("POWERGATEWAY_CONFIG", "/etc/powergateway/config.toml"))
VERSION_PATH = Path(os.environ.get("POWERGATEWAY_VERSION", "/opt/powergateway/version.txt"))
DIAGNOSTIC_COMMANDS = (
    ("PowerGateway-Dienst", ["systemctl", "is-active", "powergateway"]),
    ("Weboberfläche", ["systemctl", "is-active", "powergateway-web"]),
    ("LTE-Modem", ["mmcli", "-L"]),
    ("WireGuard", ["wg", "show"]),
    ("Serielle Geräte", ["ls", "-l", "/dev/serial/by-id"]),
)
app = Flask(__name__)

PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PowerGateway</title><style>
:root{font-family:Inter,system-ui,-apple-system,sans-serif;color:#17202a;background:#edf2f6;--nav:#132638;--muted:#657384;--ok:#147a4d;--bad:#b42318;--warn:#a15c00;--line:#e3e9ef}*{box-sizing:border-box}body{margin:0}.head{padding:22px max(4vw,20px);background:var(--nav);color:white;display:flex;justify-content:space-between;align-items:center;gap:15px}.head h1{margin:0;font-size:1.65rem}.head small{opacity:.82}.pill{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:7px 11px;background:#ffffff18;font-size:.86rem}.dot{width:9px;height:9px;border-radius:50%;background:#98a4af}.dot.ok{background:#49d18b}.dot.bad{background:#ff766e}.wrap{padding:22px max(4vw,20px);max-width:1450px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:14px}.card{background:white;border-radius:13px;padding:17px;box-shadow:0 2px 13px #16263810;border:1px solid #e8edf2}.label{font-size:.82rem;color:var(--muted)}.value{font-size:1.42rem;font-weight:720;margin-top:7px;word-break:break-word}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}h2{font-size:1.12rem;margin:0 0 14px}.section{margin-top:18px}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:650px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid var(--line);font-size:.92rem}th{color:var(--muted);font-weight:650;background:#fafcfd}.meter-value{font-weight:700}.two{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:14px}.status-list{display:grid;gap:10px}.status-row{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line);padding-bottom:9px}.status-row:last-child{border:0}.muted{color:var(--muted)}button{padding:9px 13px;border:0;border-radius:8px;cursor:pointer;background:var(--nav);color:white;font-weight:650}button:disabled{opacity:.55;cursor:wait}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#101820;color:#d7e2ed;padding:14px;border-radius:9px;font-size:.82rem}.empty{padding:25px;text-align:center;color:var(--muted)}.error-banner{display:none;background:#fff2f0;border:1px solid #ffccc7;color:#8c1d18;padding:12px 15px;border-radius:9px;margin-bottom:16px}.fresh{font-size:.82rem;color:var(--muted)}@media(max-width:900px){.two{grid-template-columns:1fr}.head{align-items:flex-start;flex-direction:column}}
</style></head><body>
<header class="head"><div><h1>PowerGateway</h1><small id="subtitle">Status wird geladen …</small></div><div class="pill"><span id="healthDot" class="dot"></span><span id="healthText">Wird geprüft</span></div></header>
<main class="wrap"><div id="error" class="error-banner"></div><section id="cards" class="grid"></section>
<section class="section card"><div class="toolbar"><div><h2>Aktuelle Zählerwerte</h2><div id="freshness" class="fresh">Noch keine Daten</div></div><button id="refreshButton" onclick="refresh()">Aktualisieren</button></div><div class="table-wrap"><table><thead><tr><th>Messwert</th><th>Wert</th><th>Einheit</th><th>OBIS</th><th>Qualität</th></tr></thead><tbody id="measurements"></tbody></table></div></section>
<section class="section two"><div class="card"><div class="toolbar"><h2>Systemdiagnose</h2><button id="diagnosticButton" onclick="loadDiagnostics()">Diagnose starten</button></div><pre id="diagnostics">Die Diagnose wird nur auf Anforderung ausgeführt.</pre></div><div class="card"><h2>Konfiguration</h2><div id="config" class="status-list"></div></div></section></main>
<script>
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=(v,fallback='—')=>v===null||v===undefined||v===''?fallback:v;
function card(label,value,state){const cls=state===true?'ok':state===false?'bad':state==='warn'?'warn':'';return `<div class="card"><div class="label">${esc(label)}</div><div class="value ${cls}">${esc(text(value))}</div></div>`}
function ageLabel(seconds){if(seconds===null||seconds===undefined)return 'noch keine Messung';if(seconds<5)return 'gerade eben';if(seconds<60)return `vor ${Math.round(seconds)} Sekunden`;if(seconds<3600)return `vor ${Math.round(seconds/60)} Minuten`;return `vor ${Math.round(seconds/3600)} Stunden`}
function configRows(c){const g=c.gateway||{},m=c.meter||{},q=c.mqtt||{},w=c.web||{},wg=c.wireguard||{};return [['Gateway',g.name],['Zählergerät',m.device||'automatisch'],['Baudrate',m.baudrate],['MQTT-Ziel',q.enabled===false?'deaktiviert':`${text(q.host)}:${text(q.port,1883)}`],['MQTT-Präfix',q.topic_prefix],['Home Assistant',q.homeassistant_discovery===false?'deaktiviert':'Discovery aktiv'],['WireGuard',wg.enabled?'aktiviert':'deaktiviert'],['Weboberfläche',`${text(w.host,'0.0.0.0')}:${text(w.port,8080)}`]].map(([k,v])=>`<div class="status-row"><span class="muted">${esc(k)}</span><strong>${esc(text(v))}</strong></div>`).join('')}
async function refresh(){const b=document.querySelector('#refreshButton');b.disabled=true;try{const r=await fetch('/_internal/overview',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);const d=await r.json(),s=d.status||{},v=d.values||{};document.querySelector('#error').style.display='none';document.querySelector('#subtitle').textContent=`Version ${d.version} · ${d.gateway_name}`;const healthy=s.meter_connected&&(!d.mqtt_enabled||s.mqtt_connected);document.querySelector('#healthDot').className=`dot ${healthy?'ok':'bad'}`;document.querySelector('#healthText').textContent=healthy?'Betriebsbereit':'Aufmerksamkeit erforderlich';document.querySelector('#cards').innerHTML=[card('Stromzähler',s.meter_connected?'Verbunden':'Getrennt',!!s.meter_connected),card('Aktuelle Leistung',v.power_total!==undefined?`${v.power_total} W`:'Noch kein Wert'),card('Energiebezug',v.energy_import!==undefined?`${v.energy_import} kWh`:'Noch kein Wert'),card('Einspeisung',v.energy_export!==undefined?`${v.energy_export} kWh`:'Noch kein Wert'),card('MQTT',d.mqtt_enabled?(s.mqtt_connected?'Verbunden':'Getrennt'):'Deaktiviert',d.mqtt_enabled?!!s.mqtt_connected:null),card('Internet',s.internet_online?'Online':'Offline',!!s.internet_online),card('LTE',`${text(s.lte_state,'Unbekannt')}${s.lte_signal?' · '+s.lte_signal:''}`),card('WireGuard',text(s.wireguard_state,'Unbekannt')),card('Telegramme',s.telegram_count||0),card('Puffer',s.buffered_messages||0,(s.buffered_messages||0)>0?'warn':null),card('Letzter Empfang',ageLabel(d.last_telegram_age_seconds),d.values_stale===true?'warn':null),card('Letzter Fehler',text(s.last_error,'Keiner'),s.last_error?false:true)].join('');const ms=v.measurements||[];document.querySelector('#measurements').innerHTML=ms.length?ms.map(x=>`<tr><td>${esc(x.name||x.key)}</td><td class="meter-value">${esc(x.value)}</td><td>${esc(text(x.unit,''))}</td><td>${esc(x.obis)}</td><td>${esc(x.quality||'gültig')}</td></tr>`).join(''):'<tr><td class="empty" colspan="5">Noch keine dekodierten Messwerte vorhanden.</td></tr>';document.querySelector('#freshness').textContent=`Letzter Empfang: ${ageLabel(d.last_telegram_age_seconds)}${d.values_stale?' · Werte möglicherweise veraltet':''}`;document.querySelector('#config').innerHTML=configRows(d.config||{})}catch(e){const box=document.querySelector('#error');box.textContent=`Status konnte nicht geladen werden: ${e.message}`;box.style.display='block';document.querySelector('#healthDot').className='dot bad';document.querySelector('#healthText').textContent='Webdienstfehler'}finally{b.disabled=false}}
async function loadDiagnostics(){const b=document.querySelector('#diagnosticButton'),p=document.querySelector('#diagnostics');b.disabled=true;p.textContent='Diagnose läuft …';try{const r=await fetch('/_internal/diagnostics',{cache:'no-store'});const d=await r.json();p.textContent=d.output||'Keine Ausgabe'}catch(e){p.textContent=`Diagnose fehlgeschlagen: ${e.message}`}finally{b.disabled=false}}
refresh();setInterval(refresh,5000);
</script></body></html>"""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def public_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, ValueError):
        return {}
    # Work on a detached JSON-compatible copy so secrets are never modified in
    # the original TOML object and nested credentials can be masked centrally.
    safe = json.loads(json.dumps(config))
    for section in safe.values():
        if not isinstance(section, dict):
            continue
        for key in tuple(section):
            if any(token in key.lower() for token in ("password", "secret", "token", "key")):
                section[key] = "********" if section[key] else ""
    return safe


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        output = (result.stdout + result.stderr).strip()
        return output or f"Keine Ausgabe (Exit-Code {result.returncode})"
    except FileNotFoundError:
        return f"Befehl nicht installiert: {command[0]}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


@app.after_request
def security_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"
    return response


@app.get("/")
def index() -> str:
    return render_template_string(PAGE)


@app.get("/health")
def health() -> Response:
    status = read_json(DATA_DIR / "status.json")
    return jsonify({"status": "ok", "meter_connected": bool(status.get("meter_connected"))})


@app.get("/_internal/overview")
def overview() -> Response:
    version = VERSION_PATH.read_text(encoding="utf-8").strip() if VERSION_PATH.exists() else "unbekannt"
    config = public_config()
    status = read_json(DATA_DIR / "status.json")
    values = read_json(DATA_DIR / "latest_values.json")
    timestamp = parse_timestamp(values.get("received_at") or status.get("last_telegram_at"))
    age = max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()) if timestamp else None
    stale_after = int(config.get("web", {}).get("stale_after_seconds", 30))
    return jsonify({
        "version": version,
        "gateway_name": config.get("gateway", {}).get("name", "PowerGateway"),
        "mqtt_enabled": bool(config.get("mqtt", {}).get("enabled", False)),
        "status": status,
        "values": values,
        "config": config,
        "last_telegram_age_seconds": age,
        "values_stale": age is None or age > stale_after,
    })


@app.get("/_internal/diagnostics")
def diagnostics() -> Response:
    parts = [f"## {title}\n$ {' '.join(command)}\n{command_output(command)}" for title, command in DIAGNOSTIC_COMMANDS]
    return jsonify({"output": "\n\n".join(parts)})


if __name__ == "__main__":
    web = public_config().get("web", {})
    app.run(host=str(web.get("host", "0.0.0.0")), port=int(web.get("port", 8080)), debug=False)
