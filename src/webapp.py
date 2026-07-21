#!/usr/bin/env python3
"""Lokale Status- und Diagnoseoberfläche für PowerGateway."""
from __future__ import annotations

import json
import os
import subprocess
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
app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PowerGateway</title><style>
:root{font-family:system-ui,sans-serif;color:#18202a;background:#eef2f6}body{margin:0}.head{padding:20px 5%;background:#162537;color:white}.head h1{margin:0}.head small{opacity:.8}.wrap{padding:22px 5%;max-width:1300px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}.card{background:white;border-radius:12px;padding:17px;box-shadow:0 2px 12px #0001}.label{font-size:.82rem;color:#667}.value{font-size:1.45rem;font-weight:700;margin-top:7px;word-break:break-word}.ok{color:#16794b}.bad{color:#b42318}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid #e8ebef}button{padding:9px 13px;border:0;border-radius:7px;cursor:pointer}pre{white-space:pre-wrap;max-height:360px;overflow:auto;background:#101820;color:#d7e2ed;padding:14px;border-radius:8px}.section{margin-top:20px}a{color:inherit}
</style></head><body><div class="head"><h1>PowerGateway</h1><small id="version">Status wird geladen …</small></div>
<div class="wrap"><div id="cards" class="grid"></div>
<div class="section card"><h2>Messwerte</h2><table><thead><tr><th>Messwert</th><th>Wert</th><th>Einheit</th><th>OBIS</th></tr></thead><tbody id="measurements"></tbody></table></div>
<div class="section grid"><div class="card"><h2>Diagnose</h2><button onclick="loadDiagnostics()">Aktualisieren</button><pre id="diagnostics">Noch nicht geladen.</pre></div><div class="card"><h2>Konfiguration</h2><pre id="config">Wird geladen …</pre></div></div></div>
<script>
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function card(label,value,good){return `<div class="card"><div class="label">${esc(label)}</div><div class="value ${good===true?'ok':good===false?'bad':''}">${esc(value)}</div></div>`}
async function refresh(){const r=await fetch('/api/overview');const d=await r.json();document.querySelector('#version').textContent=`Version ${d.version} · ${d.gateway_name}`;const s=d.status||{};document.querySelector('#cards').innerHTML=[card('Zähler',s.meter_connected?'verbunden':'getrennt',s.meter_connected),card('MQTT',s.mqtt_connected?'verbunden':'getrennt',s.mqtt_connected),card('Internet',s.internet_online?'online':'offline',s.internet_online),card('LTE',`${s.lte_state||'unbekannt'} ${s.lte_signal||''}`),card('WireGuard',s.wireguard_state||'unbekannt'),card('Telegramme',s.telegram_count||0),card('Puffer',s.buffered_messages||0),card('Letztes Telegramm',s.last_telegram_at||'noch keines')].join('');const values=d.values||{};const ms=values.measurements||[];document.querySelector('#measurements').innerHTML=ms.length?ms.map(x=>`<tr><td>${esc(x.name||x.key)}</td><td>${esc(x.value)}</td><td>${esc(x.unit)}</td><td>${esc(x.obis)}</td></tr>`).join(''):'<tr><td colspan="4">Noch keine dekodierten Messwerte vorhanden.</td></tr>';document.querySelector('#config').textContent=JSON.stringify(d.config,null,2)}
async function loadDiagnostics(){document.querySelector('#diagnostics').textContent='Diagnose läuft …';const r=await fetch('/api/diagnostics');const d=await r.json();document.querySelector('#diagnostics').textContent=d.output||d.error||'Keine Ausgabe'}
refresh();setInterval(refresh,5000);
</script></body></html>"""


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def public_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, ValueError):
        return {}
    mqtt = config.get("mqtt", {})
    if "password" in mqtt:
        mqtt["password"] = "********" if mqtt["password"] else ""
    return config


def command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        return (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


@app.get("/")
def index() -> str:
    return render_template_string(PAGE)


@app.get("/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@app.get("/api/overview")
def overview() -> Response:
    version = VERSION_PATH.read_text(encoding="utf-8").strip() if VERSION_PATH.exists() else "unbekannt"
    config = public_config()
    return jsonify({
        "version": version,
        "gateway_name": config.get("gateway", {}).get("name", "PowerGateway"),
        "status": read_json(DATA_DIR / "status.json"),
        "values": read_json(DATA_DIR / "latest_values.json"),
        "config": config,
    })


@app.get("/api/diagnostics")
def diagnostics() -> Response:
    parts = [
        "$ systemctl is-active powergateway\n" + command_output(["systemctl", "is-active", "powergateway"]),
        "$ mmcli -L\n" + command_output(["mmcli", "-L"]),
        "$ wg show\n" + command_output(["wg", "show"]),
        "$ ls -l /dev/serial/by-id\n" + command_output(["ls", "-l", "/dev/serial/by-id"]),
    ]
    return jsonify({"output": "\n\n".join(parts)})


if __name__ == "__main__":
    web = public_config().get("web", {})
    app.run(host=str(web.get("host", "0.0.0.0")), port=int(web.get("port", 8080)), debug=False)
