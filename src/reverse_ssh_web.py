#!/usr/bin/env python3
"""WebGUI und API für den allgemeinen Reverse-SSH-Fernzugriff."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import webapp_features as features
from reverse_ssh import CONFIG_PATH, KEY_PATH, STATUS_PATH, DEFAULTS

app = features.app
legacy = features.legacy
runtime = features.runtime
SERVICE = "powergateway-reverse-ssh.service"


def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout="", stderr=str(exc))


def _load(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback


def _config() -> dict[str, Any]:
    raw = _load(CONFIG_PATH, {})
    return {**DEFAULTS, **(raw if isinstance(raw, dict) else {})}


def _public_key() -> str:
    path = Path(str(KEY_PATH) + ".pub")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _state() -> dict[str, Any]:
    active = _run(["/usr/bin/systemctl", "is-active", SERVICE], 5)
    enabled = _run(["/usr/bin/systemctl", "is-enabled", SERVICE], 5)
    return {
        "active": active.stdout.strip() == "active",
        "active_state": active.stdout.strip() or "inactive",
        "enabled": enabled.stdout.strip() == "enabled",
        "enabled_state": enabled.stdout.strip() or "disabled",
        "detail": _load(STATUS_PATH, {}),
        "public_key": _public_key(),
    }


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return _run(["sudo", "-n", "/usr/bin/systemctl", *args, SERVICE])


@app.get("/_internal/reverse-ssh")
@legacy.login_required
def reverse_ssh_get() -> Response:
    return jsonify({"config": _config(), "status": _state()})


@app.post("/_internal/reverse-ssh")
@legacy.login_required
def reverse_ssh_save() -> Response:
    supplied = request.get_json(silent=True) or {}
    cfg = {**DEFAULTS, **supplied}
    try:
        for key in ("server_port", "remote_port", "local_port", "keepalive_interval", "keepalive_count_max"):
            cfg[key] = int(cfg.get(key, DEFAULTS[key]))
        if cfg.get("enabled") and not str(cfg.get("server", "")).strip():
            raise ValueError("Bitte den öffentlichen SSH-Server angeben.")
        if cfg.get("enabled") and not str(cfg.get("username", "")).strip():
            raise ValueError("Bitte den SSH-Benutzer angeben.")
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(CONFIG_PATH, 0o600)
    result = _systemctl("enable", "--now") if cfg.get("enabled") else _systemctl("disable", "--now")
    if cfg.get("enabled") and result.returncode == 0:
        result = _systemctl("restart")
    return jsonify({"ok": result.returncode == 0, "message": result.stderr.strip() or result.stdout.strip() or "Reverse-SSH gespeichert.", "status": _state()})


@app.post("/_internal/reverse-ssh/key")
@legacy.login_required
def reverse_ssh_key() -> Response:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        return jsonify({"ok": True, "public_key": _public_key(), "message": "Vorhandener Schlüssel wird verwendet."})
    result = _run(["/usr/bin/ssh-keygen", "-t", "ed25519", "-N", "", "-C", "powergateway-reverse-ssh", "-f", str(KEY_PATH)], 30)
    if result.returncode != 0:
        return jsonify({"error": result.stderr.strip() or "Schlüssel konnte nicht erzeugt werden."}), 500
    os.chmod(KEY_PATH, 0o600)
    os.chmod(Path(str(KEY_PATH) + ".pub"), 0o644)
    return jsonify({"ok": True, "public_key": _public_key(), "message": "SSH-Schlüsselpaar erzeugt."})


@app.post("/_internal/reverse-ssh/action/<action>")
@legacy.login_required
def reverse_ssh_action(action: str) -> Response:
    if action not in {"start", "restart", "stop"}:
        return jsonify({"error": "Unbekannte Aktion."}), 400
    args = ("enable", "--now") if action == "start" else (("disable", "--now") if action == "stop" else ("restart",))
    result = _systemctl(*args)
    return jsonify({"ok": result.returncode == 0, "message": result.stderr.strip() or result.stdout.strip() or f"Aktion {action} ausgeführt.", "status": _state()}), 200 if result.returncode == 0 else 500


@app.get("/_internal/reverse-ssh/logs")
@legacy.login_required
def reverse_ssh_logs() -> Response:
    result = _run(["/usr/bin/journalctl", "-u", SERVICE, "-n", "100", "--no-pager", "-o", "short-iso"], 10)
    return jsonify({"ok": result.returncode == 0, "logs": result.stdout[-30000:], "error": result.stderr.strip()})


SECTION = r'''
<section id="reverseSsh" class="tab"><div class="toolbar"><div><h2>Reverse-SSH</h2><div class="muted">Sicherer Fernzugriff auch hinter LTE-NAT oder CGNAT.</div></div><button onclick="saveReverseSsh()">Speichern und anwenden</button></div><div id="rssCards" class="grid"></div><div class="section two"><div class="card"><h3>Server und Tunnel</h3><div class="form-grid"><label class="check full"><input id="rssEnabled" type="checkbox"> Reverse-SSH aktivieren</label><div class="field full"><label>Öffentlicher SSH-Server</label><input id="rssServer" placeholder="server.example.de"></div><div class="field"><label>Server-Port</label><input id="rssServerPort" type="number" value="22"></div><div class="field"><label>SSH-Benutzer</label><input id="rssUsername" value="powergateway"></div><div class="field"><label>Remote-Bind-Adresse</label><input id="rssBind" value="127.0.0.1"></div><div class="field"><label>Remote-Port</label><input id="rssRemotePort" type="number" value="2222"></div><div class="field"><label>Lokales Ziel</label><input id="rssLocalHost" value="127.0.0.1"></div><div class="field"><label>Lokaler SSH-Port</label><input id="rssLocalPort" type="number" value="22"></div></div></div><div class="card"><h3>SSH-Schlüssel</h3><p class="muted">Diesen öffentlichen Schlüssel auf dem Zielserver beim angegebenen Benutzer in <code>~/.ssh/authorized_keys</code> eintragen.</p><textarea id="rssPublicKey" readonly style="width:100%;min-height:130px"></textarea><div class="toolbar"><button class="secondary" onclick="generateReverseSshKey()">Schlüssel erzeugen</button><button class="secondary" onclick="copyReverseSshKey()">Kopieren</button></div><p class="muted">Verbindung vom Server: <code id="rssConnectHint">ssh -p 2222 admin@localhost</code></p></div></div><div class="section card"><div class="toolbar"><h3>Dienststeuerung</h3><div><button class="secondary" onclick="reverseSshAction('start')">Starten</button> <button class="secondary" onclick="reverseSshAction('restart')">Neu starten</button> <button class="secondary" onclick="reverseSshAction('stop')">Stoppen</button> <button class="secondary" onclick="loadReverseSshLogs()">Logs</button></div></div><pre id="rssLogs">Noch nicht geladen.</pre></div></section>
'''

JS = r'''
async function loadReverseSsh(){try{const d=await api('/_internal/reverse-ssh'),c=d.config||{},s=d.status||{};chk('rssEnabled',c.enabled);val('rssServer',c.server);val('rssServerPort',c.server_port||22);val('rssUsername',c.username||'powergateway');val('rssBind',c.remote_bind_address||'127.0.0.1');val('rssRemotePort',c.remote_port||2222);val('rssLocalHost',c.local_host||'127.0.0.1');val('rssLocalPort',c.local_port||22);val('rssPublicKey',s.public_key||'Noch kein Schlüssel erzeugt.');$('rssConnectHint').textContent=`ssh -p ${c.remote_port||2222} admin@localhost`;$('rssCards').innerHTML=[card('Dienst',s.active?'Aktiv':'Inaktiv',s.active?'ok':'bad'),card('Autostart',s.enabled?'Aktiv':'Aus',s.enabled?'ok':'warn'),card('Server',c.server||'—'),card('Remote-Port',c.remote_port||2222)].join('')}catch(e){notice(e.message,false)}}
async function saveReverseSsh(){const body={enabled:$('rssEnabled').checked,server:$('rssServer').value.trim(),server_port:Number($('rssServerPort').value||22),username:$('rssUsername').value.trim(),remote_bind_address:$('rssBind').value.trim()||'127.0.0.1',remote_port:Number($('rssRemotePort').value||2222),local_host:$('rssLocalHost').value.trim()||'127.0.0.1',local_port:Number($('rssLocalPort').value||22),keepalive_interval:30,keepalive_count_max:3};try{const d=await api('/_internal/reverse-ssh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});notice(d.message,d.ok!==false);await loadReverseSsh()}catch(e){notice(e.message,false)}}
async function generateReverseSshKey(){try{const d=await api('/_internal/reverse-ssh/key',{method:'POST'});val('rssPublicKey',d.public_key);notice(d.message)}catch(e){notice(e.message,false)}}
async function copyReverseSshKey(){try{await navigator.clipboard.writeText($('rssPublicKey').value);notice('Öffentlicher Schlüssel kopiert.')}catch(e){notice('Kopieren nicht möglich.',false)}}
async function reverseSshAction(a){try{const d=await api('/_internal/reverse-ssh/action/'+a,{method:'POST'});notice(d.message,d.ok!==false);await loadReverseSsh()}catch(e){notice(e.message,false)}}
async function loadReverseSshLogs(){try{const d=await api('/_internal/reverse-ssh/logs');$('rssLogs').textContent=d.logs||d.error||'Keine Einträge.'}catch(e){$('rssLogs').textContent=e.message}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'reverseSsh\',this)">Fernzugriff</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users" class="tab">', SECTION + '<section id="users" class="tab">')
page = page.replace("if(id==='users')loadUsers();", "if(id==='reverseSsh')loadReverseSsh();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
