#!/usr/bin/env python3
"""Zentraler Internetmanager für Netzwerk, VPN, DDNS, MQTT und Systemstatus."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from flask import Response, jsonify

import webapp_features as features
from noip_client import load_config as load_noip_config, load_status as load_noip_status

app = features.app
legacy = features.legacy
runtime = features.runtime
DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
EVENT_PATH = DATA_DIR / "internet_manager_events.json"
MAX_EVENTS = 100


def _run(args: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout="", stderr=str(exc))


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback


def _service(name: str) -> dict[str, Any]:
    result = _run(["/usr/bin/systemctl", "is-active", name], 5)
    state = result.stdout.strip() or "inactive"
    return {"ok": state == "active", "state": state, "service": name}


def _default_routes() -> list[dict[str, Any]]:
    result = _run(["/usr/sbin/ip", "-4", "route", "show", "default"], 5)
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts or parts[0] != "default":
            continue
        row: dict[str, Any] = {"raw": line}
        for key in ("via", "dev", "src", "metric"):
            if key in parts and parts.index(key) + 1 < len(parts):
                row[key] = parts[parts.index(key) + 1]
        try:
            row["metric"] = int(row.get("metric", 0))
        except (TypeError, ValueError):
            row["metric"] = 0
        rows.append(row)
    return sorted(rows, key=lambda item: item.get("metric", 0))


def _addresses(interface: str) -> list[str]:
    result = _run(["/usr/sbin/ip", "-o", "-4", "addr", "show", "dev", interface], 5)
    values: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if "inet" in parts and parts.index("inet") + 1 < len(parts):
            values.append(parts[parts.index("inet") + 1])
    return values


def _link(interface: str, route: dict[str, Any] | None = None) -> dict[str, Any]:
    exists = Path("/sys/class/net") .joinpath(interface).exists()
    state = "missing"
    if exists:
        try:
            state = Path("/sys/class/net", interface, "operstate").read_text(encoding="utf-8").strip()
        except OSError:
            state = "unknown"
    return {
        "interface": interface,
        "exists": exists,
        "state": state,
        "up": state in {"up", "unknown"},
        "addresses": _addresses(interface) if exists else [],
        "gateway": (route or {}).get("via"),
        "metric": (route or {}).get("metric"),
        "default_route": bool(route),
    }


def _active_gateway() -> dict[str, Any]:
    routes = _default_routes()
    active = routes[0] if routes else {}
    interface = str(active.get("dev", ""))
    kind = "lte" if interface.startswith(("wwan", "usb")) or interface == "eth1" else "wifi" if interface.startswith("wl") else "lan" if interface else "none"
    return {"kind": kind, "interface": interface, "gateway": active.get("via"), "metric": active.get("metric"), "routes": routes}


def _tcp(host: str, port: int, timeout: float = 3.0) -> dict[str, Any]:
    if not host:
        return {"ok": False, "message": "Nicht konfiguriert"}
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "message": "Erreichbar", "latency_ms": round((time.monotonic() - started) * 1000, 1)}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def _dns() -> dict[str, Any]:
    started = time.monotonic()
    try:
        values = sorted({row[4][0] for row in socket.getaddrinfo("www.debian.org", 443, socket.AF_INET, socket.SOCK_STREAM)})
        return {"ok": bool(values), "message": ", ".join(values), "latency_ms": round((time.monotonic() - started) * 1000, 1)}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def _internet() -> dict[str, Any]:
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        result = _tcp(host, port, 4)
        if result.get("ok"):
            result.update({"target": f"{host}:{port}"})
            return result
    return {"ok": False, "message": "Kein Internet-Testziel erreichbar"}


def _system() -> dict[str, Any]:
    uptime = 0.0
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    memory: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0])
    except (OSError, ValueError):
        pass
    total = memory.get("MemTotal", 0)
    available = memory.get("MemAvailable", 0)
    disk = shutil.disk_usage("/")
    temperature = None
    try:
        temperature = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    return {
        "uptime_seconds": int(uptime),
        "load": list(os.getloadavg()),
        "memory_total_mb": round(total / 1024),
        "memory_used_percent": round((total - available) * 100 / total, 1) if total else None,
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_used_percent": round(disk.used * 100 / disk.total, 1),
        "temperature_c": temperature,
    }


def _mqtt_config() -> dict[str, Any]:
    candidates = [DATA_DIR / "runtime_config.json", DATA_DIR / "config.json", Path("/etc/powergateway/config.json")]
    for path in candidates:
        value = _read_json(path, {})
        if not isinstance(value, dict):
            continue
        mqtt = value.get("mqtt") if isinstance(value.get("mqtt"), dict) else value
        host = mqtt.get("host") or mqtt.get("mqtt_host") or mqtt.get("broker")
        port = mqtt.get("port") or mqtt.get("mqtt_port") or 1883
        if host:
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 1883
            return {"host": str(host), "port": port}
    return {"host": "", "port": 1883}


def _homeassistant_config() -> dict[str, Any]:
    value = _read_json(DATA_DIR / "homeassistant_config.json", {})
    return value if isinstance(value, dict) else {}


def _event_snapshot(status: dict[str, Any]) -> None:
    previous_rows = _read_json(EVENT_PATH, [])
    rows = previous_rows if isinstance(previous_rows, list) else []
    previous = rows[-1].get("snapshot", {}) if rows and isinstance(rows[-1], dict) else {}
    snapshot = {
        "gateway": status.get("gateway", {}).get("interface"),
        "online": status.get("internet", {}).get("ok"),
        "wireguard": status.get("wireguard", {}).get("ok"),
        "ddns": status.get("ddns", {}).get("ok"),
    }
    if snapshot != previous:
        labels = []
        if snapshot.get("gateway") != previous.get("gateway"):
            labels.append(f"Gateway: {snapshot.get('gateway') or 'keins'}")
        if snapshot.get("online") != previous.get("online"):
            labels.append("Internet verfügbar" if snapshot.get("online") else "Internet ausgefallen")
        if snapshot.get("wireguard") != previous.get("wireguard"):
            labels.append("WireGuard aktiv" if snapshot.get("wireguard") else "WireGuard inaktiv")
        if snapshot.get("ddns") != previous.get("ddns"):
            labels.append("DDNS OK" if snapshot.get("ddns") else "DDNS gestört")
        rows.append({"timestamp": int(time.time()), "message": " · ".join(labels) or "Status geändert", "snapshot": snapshot})
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVENT_PATH.write_text(json.dumps(rows[-MAX_EVENTS:], ensure_ascii=False, indent=2), encoding="utf-8")


def collect_status(run_tests: bool = False) -> dict[str, Any]:
    gateway = _active_gateway()
    route_by_interface = {str(row.get("dev")): row for row in gateway.get("routes", [])}
    links = {
        "lan": _link("eth0", route_by_interface.get("eth0")),
        "wifi": _link("wlan0", route_by_interface.get("wlan0")),
        "lte": _link("eth1", route_by_interface.get("eth1")),
    }
    noip_config = load_noip_config()
    noip_status = load_noip_status()
    mqtt = _mqtt_config()
    ha = _homeassistant_config()
    result: dict[str, Any] = {
        "timestamp": int(time.time()),
        "gateway": gateway,
        "links": links,
        "internet": _internet(),
        "dns": _dns(),
        "wireguard": _service("wg-quick@wg0.service"),
        "ssh_tunnel": _service("powergateway-ha-tunnel.service"),
        "ddns": {
            "ok": bool(noip_status.get("ok")),
            "enabled": bool(noip_config.get("enabled")),
            "hostname": noip_config.get("hostname", ""),
            "public_ipv4": noip_status.get("public_ipv4"),
            "status": noip_status.get("status", "unknown"),
            "message": noip_status.get("message", "Noch kein Update"),
            "last_success_at": noip_status.get("last_success_at"),
        },
        "mqtt": {**mqtt, **_tcp(str(mqtt.get("host", "")), int(mqtt.get("port", 1883)))},
        "homeassistant": {
            "enabled": bool(ha.get("enabled")),
            "mode": ha.get("mode", ""),
            "host": ha.get("ha_host", ""),
            "port": ha.get("ha_port", 8123),
            **_tcp(str(ha.get("ha_host", "")), int(ha.get("ha_port", 8123) or 8123)),
        },
        "system": _system(),
    }
    if run_tests:
        result["tests_run"] = True
    _event_snapshot(result)
    result["events"] = _read_json(EVENT_PATH, [])[-30:]
    return result


@app.get("/_internal/internet-manager")
@legacy.login_required
def internet_manager_status() -> Response:
    return jsonify(collect_status(False))


@app.post("/_internal/internet-manager/test")
@legacy.login_required
def internet_manager_test() -> Response:
    return jsonify(collect_status(True))


SECTION = r'''
<section id="internetManager" class="tab"><div class="toolbar"><div><h2>Internetmanager</h2><div class="muted">Zentrale Übersicht für Internet, LAN, WLAN, LTE, VPN, DDNS, MQTT und Home Assistant.</div></div><div><button onclick="loadInternetManager()">Aktualisieren</button> <button class="secondary" onclick="testInternetManager()">Alles testen</button></div></div><div id="imCards" class="grid"></div><div class="section two"><div class="card"><h3>Netzwerkverbindungen</h3><div id="imLinks">Wird geladen …</div></div><div class="card"><h3>Systemmonitor</h3><div id="imSystem">Wird geladen …</div></div></div><div class="section"><h3>Ereignisverlauf</h3><div id="imEvents" class="muted">Noch keine Ereignisse.</div></div><div class="section"><h3>Vollständige Diagnose</h3><pre id="imRaw" style="max-height:420px;overflow:auto">Noch nicht geladen.</pre></div></section>
'''

JS = r'''
function imBadge(ok){return `<span class="badge ${ok?'ok':'bad'}">${ok?'OK':'Störung'}</span>`}
function imRow(label,value){return `<div class="status-row"><span>${esc(label)}</span><strong>${esc(value===undefined||value===null||value===''?'—':String(value))}</strong></div>`}
function imCard(title,ok,rows){return `<div class="card"><div class="toolbar"><h3>${esc(title)}</h3>${imBadge(ok)}</div>${rows}</div>`}
function renderInternetManager(d){const g=d.gateway||{},dd=d.ddns||{},wg=d.wireguard||{},mq=d.mqtt||{},ha=d.homeassistant||{},net=d.internet||{},dns=d.dns||{};$('imCards').innerHTML=[imCard('Internet',!!net.ok,imRow('Aktives Gateway',(g.kind||'—').toUpperCase()+' · '+(g.interface||'—'))+imRow('Gateway',g.gateway)+imRow('Verbindung',net.message)+imRow('DNS',dns.ok?'OK':'Fehler')),imCard('VPN',!!wg.ok,imRow('WireGuard',wg.state)+imRow('SSH-Tunnel',(d.ssh_tunnel||{}).state)),imCard('DDNS',!!dd.ok,imRow('Hostname',dd.hostname)+imRow('Öffentliche IPv4',dd.public_ipv4)+imRow('Status',dd.message)),imCard('MQTT',!!mq.ok,imRow('Broker',mq.host)+imRow('Port',mq.port)+imRow('Status',mq.message)),imCard('Home Assistant',!!ha.ok,imRow('Host',ha.host)+imRow('Modus',ha.mode)+imRow('Status',ha.message))].join('');$('imLinks').innerHTML=Object.entries(d.links||{}).map(([name,x])=>`<div class="status-row"><span>${esc(name.toUpperCase())} · ${esc(x.interface)}</span><strong>${x.up?'aktiv':'inaktiv'} · ${esc((x.addresses||[]).join(', ')||'keine IP')} · GW ${esc(x.gateway||'—')}</strong></div>`).join('');const s=d.system||{};$('imSystem').innerHTML=imRow('Uptime',Math.floor((s.uptime_seconds||0)/3600)+' h')+imRow('CPU Load',(s.load||[]).map(x=>Number(x).toFixed(2)).join(' / '))+imRow('RAM',s.memory_used_percent+' %')+imRow('Speicher',s.disk_used_percent+' %')+imRow('Temperatur',s.temperature_c===null?'—':s.temperature_c+' °C');$('imEvents').innerHTML=(d.events||[]).slice().reverse().map(e=>`<div class="status-row"><span>${esc(new Date(e.timestamp*1000).toLocaleString())}</span><strong>${esc(e.message||'')}</strong></div>`).join('')||'Noch keine Ereignisse.';$('imRaw').textContent=JSON.stringify(d,null,2)}
async function loadInternetManager(){try{renderInternetManager(await api('/_internal/internet-manager'))}catch(e){notice(e.message,false)}}
async function testInternetManager(){try{const d=await api('/_internal/internet-manager/test',{method:'POST'});renderInternetManager(d);notice('Alle Internetmanager-Tests wurden ausgeführt.',true)}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'network\',this)">Netzwerk</button>', '<button onclick="showTab(\'internetManager\',this)">Internetmanager</button><button onclick="showTab(\'network\',this)">Netzwerk</button>')
page = page.replace('<section id="network"', SECTION + '<section id="network"')
page = page.replace("if(id==='network')", "if(id==='internetManager')loadInternetManager();if(id==='network')")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
