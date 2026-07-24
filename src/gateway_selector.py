#!/usr/bin/env python3
"""Auswahl des bevorzugten aktiven Standard-Gateways in der WebGUI."""
from __future__ import annotations

from typing import Any

from flask import Response, jsonify, request

import webapp_features as features

app = features.app
legacy = features.legacy
runtime = features.runtime

ALLOWED = {"auto", "lan", "wifi", "lte"}


def _current_config() -> dict[str, Any]:
    return legacy.network_config(True)


def _status() -> dict[str, Any]:
    config = legacy.network_config(False)
    network_status = legacy.read_json(legacy.NETWORK_STATUS_PATH)
    order = [str(item).lower() for item in config.get("priority", ["lan", "wifi", "lte"])]
    preferred = str(config.get("preferred_gateway", "auto")).lower()
    if preferred not in ALLOWED:
        preferred = "auto"
    return {
        "preferred": preferred,
        "active": network_status.get("active", "none"),
        "online": bool(network_status.get("online")),
        "priority": order,
        "links": {
            name: network_status.get(name, {})
            for name in ("lan", "wifi", "lte")
        },
    }


@app.get("/_internal/network/gateway")
@legacy.login_required
def gateway_status() -> Response:
    return jsonify(_status())


@app.post("/_internal/network/gateway")
@legacy.login_required
def gateway_select() -> tuple[Response, int] | Response:
    supplied = request.get_json(silent=True) or {}
    preferred = str(supplied.get("gateway", "auto")).strip().lower()
    if preferred not in ALLOWED:
        return jsonify({"error": "Ungültiges Gateway. Erlaubt sind automatisch, LAN, WLAN und LTE."}), 400

    config = _current_config()
    old_order = [str(item).lower() for item in config.get("priority", ["lan", "wifi", "lte"])]
    order = [item for item in old_order if item in {"lan", "wifi", "lte"}]
    for item in ("lan", "wifi", "lte"):
        if item not in order:
            order.append(item)

    if preferred != "auto":
        order = [preferred] + [item for item in order if item != preferred]

    config["preferred_gateway"] = preferred
    config["priority"] = order
    legacy.atomic_json(legacy.NETWORK_CONFIG_PATH, config)

    label = {"auto": "Automatisch", "lan": "LAN", "wifi": "WLAN", "lte": "LTE"}[preferred]
    result = _status()
    result.update({
        "ok": True,
        "message": f"Bevorzugtes Gateway wurde auf {label} gesetzt. Die Route wird innerhalb weniger Sekunden neu bewertet.",
    })
    return jsonify(result)


SECTION = r'''
<div class="section card"><div class="toolbar"><div><h2>Aktives Internet-Gateway</h2><div class="muted">Legt fest, welche Verbindung als Standardweg ins Internet bevorzugt wird. Fällt sie aus, verwendet PowerGateway die nächste verfügbare Verbindung.</div></div><button onclick="applyGatewaySelection()">Gateway setzen</button></div><div class="form-grid"><div class="field"><label>Bevorzugtes Gateway</label><select id="preferredGateway"><option value="auto">Automatisch nach Priorität</option><option value="lan">LAN</option><option value="wifi">WLAN</option><option value="lte">LTE</option></select></div><div class="field"><label>Aktuell verwendet</label><input id="activeGatewayDisplay" readonly value="Wird geladen …"></div></div><div id="gatewayDetail" class="section muted">Noch nicht geprüft.</div></div>
'''

JS = r'''
function gatewayLabel(v){return v==='lan'?'LAN':v==='wifi'?'WLAN':v==='lte'?'LTE':v==='auto'?'Automatisch':'Keine'}
async function loadGatewaySelection(){try{const d=await api('/_internal/network/gateway');val('preferredGateway',d.preferred||'auto');val('activeGatewayDisplay',gatewayLabel(d.active));const p=(d.priority||[]).map(gatewayLabel).join(' → ');$('gatewayDetail').textContent=`Priorität: ${p||'—'} · Internet: ${d.online?'verfügbar':'nicht verfügbar'}`}catch(e){$('gatewayDetail').textContent=e.message}}
async function applyGatewaySelection(){try{const d=await api('/_internal/network/gateway',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gateway:$('preferredGateway').value})});notice(d.message,d.ok!==false);setTimeout(()=>{loadGatewaySelection();loadNetwork()},3000)}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<div id="networkCards" class="grid"></div><div class="section two">', '<div id="networkCards" class="grid"></div>' + SECTION + '<div class="section two">')
page = page.replace("if(id==='network')loadNetwork();", "if(id==='network'){loadNetwork();loadGatewaySelection();}")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
