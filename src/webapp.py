#!/usr/bin/env python3
"""Lokale Administrationsoberfläche für PowerGateway."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, Response, jsonify, redirect, render_template_string, request, session, url_for

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

from auth_store import change_password, create_user, has_users, list_users, verify_user
from network_manager import wifi_scan

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA", "/var/lib/powergateway"))
CONFIG_PATH = Path(os.environ.get("POWERGATEWAY_CONFIG", "/etc/powergateway/config.toml"))
VERSION_PATH = Path(os.environ.get("POWERGATEWAY_VERSION", "/opt/powergateway/version.txt"))
USERS_PATH = DATA_DIR / "users.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
SECRET_PATH = DATA_DIR / "web_secret"
NETWORK_CONFIG_PATH = DATA_DIR / "network_config.json"
NETWORK_STATUS_PATH = DATA_DIR / "network_status.json"
NETWORK_RESULT_PATH = DATA_DIR / "network_result.json"

app = Flask(__name__)


def _web_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        value = SECRET_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    value = secrets.token_hex(32)
    SECRET_PATH.write_text(value, encoding="utf-8")
    os.chmod(SECRET_PATH, 0o600)
    return value


app.secret_key = _web_secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", PERMANENT_SESSION_LIFETIME=3600)

STYLE = """
:root{font-family:Inter,system-ui,sans-serif;color:#17202a;background:#edf2f6;--nav:#132638;--muted:#657384;--ok:#147a4d;--bad:#b42318;--warn:#a15c00;--line:#e3e9ef}*{box-sizing:border-box}body{margin:0}.head{padding:18px max(4vw,20px);background:var(--nav);color:#fff;display:flex;justify-content:space-between;align-items:center;gap:12px}.head h1{margin:0;font-size:1.55rem}.head small{opacity:.8}.nav{background:#fff;border-bottom:1px solid var(--line);padding:0 max(4vw,20px);display:flex;gap:4px;overflow:auto}.nav button{background:transparent;color:var(--nav);border-radius:0;padding:14px 16px;border-bottom:3px solid transparent;white-space:nowrap}.nav button.active{border-bottom-color:var(--nav)}.wrap{padding:20px max(4vw,20px);max-width:1450px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card{background:#fff;border-radius:13px;padding:17px;box-shadow:0 2px 13px #16263810;border:1px solid #e8edf2}.label{font-size:.82rem;color:var(--muted)}.value{font-size:1.35rem;font-weight:720;margin-top:7px;word-break:break-word}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}h2{font-size:1.12rem;margin:0 0 14px}.section{margin-top:18px}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.field{display:grid;gap:5px}.field.full{grid-column:1/-1}label{font-size:.84rem;color:var(--muted);font-weight:650}input,select{width:100%;padding:10px;border:1px solid #ccd5de;border-radius:8px;background:#fff;font:inherit}.check{display:flex;align-items:center;gap:9px}.check input{width:auto}button,.button{padding:9px 13px;border:0;border-radius:8px;cursor:pointer;background:var(--nav);color:#fff;font-weight:650;text-decoration:none;display:inline-block}button.secondary,.button.secondary{background:#e9eef3;color:var(--nav)}.status-row{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line);padding:9px 0}.muted{color:var(--muted)}.notice{display:none;padding:12px 15px;border-radius:9px;margin-bottom:15px}.notice.ok{display:block;background:#edf9f2;border:1px solid #b7e4c7}.notice.bad{display:block;background:#fff2f0;border:1px solid #ffccc7}.tab{display:none}.tab.active{display:block}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;background:#101820;color:#d7e2ed;padding:14px;border-radius:9px;max-height:420px;overflow:auto}.center{max-width:650px;margin:7vh auto;padding:20px}.steps{display:flex;gap:8px;margin-bottom:18px}.step{height:6px;flex:1;background:#dce3e9;border-radius:9px}.step.active{background:var(--nav)}@media(max-width:900px){.two,.form-grid{grid-template-columns:1fr}.head{align-items:flex-start;flex-direction:column}}
"""

LOGIN_PAGE = """<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Anmelden</title><style>""" + STYLE + """</style></head><body><main class='center'><div class='card'><h1>PowerGateway</h1><p class='muted'>Bitte melden Sie sich an.</p>{% if error %}<p class='bad'>{{ error }}</p>{% endif %}<form method='post' class='form-grid'><div class='field full'><label>Benutzername</label><input name='username' autocomplete='username' required autofocus></div><div class='field full'><label>Passwort</label><input name='password' type='password' autocomplete='current-password' required></div><div class='field full'><button>Anmelden</button></div></form></div></main></body></html>"""

SETUP_PAGE = """<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Ersteinrichtung</title><style>""" + STYLE + """</style></head><body><main class='center'><div class='card'><div class='steps'><span class='step active'></span><span class='step active'></span><span class='step active'></span></div><h1>PowerGateway einrichten</h1><p class='muted'>Legen Sie den Gerätenamen und das erste Administratorkonto an.</p>{% if error %}<p class='bad'>{{ error }}</p>{% endif %}<form method='post' class='form-grid'><div class='field full'><label>Gerätename</label><input name='gateway_name' value='{{ gateway_name }}' required></div><div class='field full'><label>Administrator-Benutzername</label><input name='username' value='admin' autocomplete='username' required></div><div class='field'><label>Passwort</label><input name='password' type='password' autocomplete='new-password' required></div><div class='field'><label>Passwort wiederholen</label><input name='password_confirm' type='password' autocomplete='new-password' required></div><div class='field full'><button>Einrichtung abschließen</button></div></form><p class='muted'>Mindestens 10 Zeichen, Groß- und Kleinbuchstaben sowie eine Zahl.</p></div></main></body></html>"""

PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PowerGateway</title><style>__STYLE__</style></head><body>
<header class="head"><div><h1>PowerGateway</h1><small id="subtitle">Status wird geladen …</small></div><div><strong id="health">Wird geprüft</strong> · <a class="button secondary" href="/logout">Abmelden</a></div></header>
<nav class="nav"><button class="active" onclick="showTab('dashboard',this)">Dashboard</button><button onclick="showTab('network',this)">Netzwerk</button><button onclick="showTab('users',this)">Benutzer</button><button onclick="showTab('diagnostics',this)">Diagnose</button></nav>
<main class="wrap"><div id="notice" class="notice"></div>
<section id="dashboard" class="tab active"><div id="cards" class="grid"></div><div class="section card"><h2>Aktuelle Zählerwerte</h2><table><thead><tr><th>Messwert</th><th>Wert</th><th>Einheit</th><th>OBIS</th></tr></thead><tbody id="measurements"></tbody></table></div></section>
<section id="network" class="tab"><div class="toolbar"><div><h2>Netzwerkverwaltung</h2><div class="muted">LAN, WLAN, LTE und Setup-Hotspot</div></div><button onclick="saveNetwork()">Speichern und anwenden</button></div><div id="networkCards" class="grid"></div><div class="section two">
<div class="card"><h2>Priorität und LAN</h2><div class="form-grid"><div class="field"><label>1. Verbindung</label><select id="prio1"><option value="lan">LAN</option><option value="wifi">WLAN</option><option value="lte">LTE</option></select></div><div class="field"><label>2. Verbindung</label><select id="prio2"><option value="wifi">WLAN</option><option value="lan">LAN</option><option value="lte">LTE</option></select></div><div class="field"><label>3. Verbindung</label><select id="prio3"><option value="lte">LTE</option><option value="wifi">WLAN</option><option value="lan">LAN</option></select></div><label class="check"><input id="lanEnabled" type="checkbox"> LAN aktiv</label><label class="check"><input id="lanDhcp" type="checkbox"> DHCP</label><div class="field"><label>Schnittstelle</label><input id="lanInterface"></div><div class="field"><label>Profilname</label><input id="lanConnection"></div><div class="field"><label>IP/CIDR</label><input id="lanAddress"></div><div class="field"><label>Gateway</label><input id="lanGateway"></div><div class="field full"><label>DNS (Komma)</label><input id="lanDns"></div></div></div>
<div class="card"><div class="toolbar"><h2>WLAN</h2><button class="secondary" onclick="scanWifi()">Suchen</button></div><div class="form-grid"><label class="check full"><input id="wifiEnabled" type="checkbox"> WLAN aktiv</label><div class="field"><label>Schnittstelle</label><input id="wifiInterface"></div><div class="field"><label>Profilname</label><input id="wifiConnection"></div><div class="field full"><label>SSID</label><input id="wifiSsid"></div><div class="field full"><label>Passwort</label><input id="wifiPassword" type="password" placeholder="Leer = beibehalten"></div></div><div id="wifiList" class="section muted">Noch keine Suche.</div></div></div>
<div class="section two"><div class="card"><h2>LTE</h2><div class="form-grid"><label class="check full"><input id="lteEnabled" type="checkbox"> LTE aktiv</label><div class="field"><label>Profilname</label><input id="lteConnection"></div><div class="field"><label>APN</label><input id="lteApn"></div><div class="field"><label>Benutzername</label><input id="lteUsername"></div><div class="field"><label>Passwort</label><input id="ltePassword" type="password"></div><div class="field"><label>SIM-PIN</label><input id="ltePin" type="password"></div></div></div><div class="card"><h2>Setup-Hotspot</h2><div class="form-grid"><div class="field"><label>Betriebsart</label><select id="hotspotMode"><option value="auto">Automatisch</option><option value="always">Immer an</option><option value="off">Aus</option></select></div><div class="field"><label>Schnittstelle</label><input id="hotspotInterface"></div><div class="field"><label>SSID</label><input id="hotspotSsid"></div><div class="field"><label>Passwort</label><input id="hotspotPassword" type="password" placeholder="Leer = beibehalten"></div><div class="field"><label>IP/CIDR</label><input id="hotspotAddress"></div><label class="check"><input id="hotspotOffline" type="checkbox"> Ohne Internet starten</label></div></div></div></section>
<section id="users" class="tab"><div class="two"><div class="card"><h2>Benutzer</h2><div id="userList"></div></div><div class="card"><h2>Eigenes Passwort ändern</h2><div class="form-grid"><div class="field full"><label>Aktuelles Passwort</label><input id="oldPassword" type="password"></div><div class="field"><label>Neues Passwort</label><input id="newPassword" type="password"></div><div class="field"><label>Wiederholen</label><input id="newPassword2" type="password"></div><div class="field full"><button onclick="changePassword()">Passwort ändern</button></div></div></div></div></section>
<section id="diagnostics" class="tab"><div class="toolbar"><h2>Systemdiagnose</h2><button onclick="loadDiagnostics()">Diagnose starten</button></div><pre id="diagnosticOutput">Die Diagnose wird nur auf Anforderung ausgeführt.</pre></section></main>
<script>
const $=id=>document.getElementById(id),esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function showTab(id,b){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active'));$(id).classList.add('active');b.classList.add('active');if(id==='network')loadNetwork();if(id==='users')loadUsers()}
function card(l,v,s=''){return `<div class="card"><div class="label">${esc(l)}</div><div class="value ${s}">${esc(v)}</div></div>`}function notice(t,o=true){const n=$('notice');n.textContent=t;n.className='notice '+(o?'ok':'bad');setTimeout(()=>n.className='notice',6000)}function val(i,v=''){$(i).value=v??''}function chk(i,v){$(i).checked=!!v}
async function api(url,opt={}){const r=await fetch(url,{cache:'no-store',...opt});if(r.status===401){location='/login';throw new Error('Sitzung abgelaufen')}const d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);return d}
async function refresh(){try{const d=await api('/_internal/overview'),s=d.status||{},v=d.values||{},n=d.network||{};$('subtitle').textContent=`Version ${d.version} · ${d.gateway_name}`;$('health').textContent=s.meter_connected?'Betriebsbereit':'Prüfung erforderlich';$('cards').innerHTML=[card('Stromzähler',s.meter_connected?'Verbunden':'Getrennt',s.meter_connected?'ok':'bad'),card('Leistung',v.power_total!==undefined?`${v.power_total} W`:'Noch kein Wert'),card('MQTT',s.mqtt_connected?'Verbunden':'Getrennt',s.mqtt_connected?'ok':'bad'),card('Aktive Verbindung',(n.active||'keine').toUpperCase(),n.online?'ok':'bad'),card('Setup-Hotspot',n.hotspot_active?'Aktiv':'Inaktiv',n.hotspot_active?'warn':''),card('Angemeldet',d.current_user||'—')].join('');const ms=v.measurements||[];$('measurements').innerHTML=ms.length?ms.map(x=>`<tr><td>${esc(x.name||x.key)}</td><td>${esc(x.value)}</td><td>${esc(x.unit||'')}</td><td>${esc(x.obis||'')}</td></tr>`).join(''):'<tr><td colspan="4">Noch keine Messwerte vorhanden.</td></tr>'}catch(e){notice(e.message,false)}}
async function loadNetwork(){try{const d=await api('/_internal/network'),c=d.config||{},s=d.status||{},p=c.priority||['lan','wifi','lte'];['prio1','prio2','prio3'].forEach((id,i)=>val(id,p[i]));const l=c.lan||{},w=c.wifi||{},m=c.lte||{},h=c.hotspot||{};chk('lanEnabled',l.enabled);chk('lanDhcp',l.dhcp!==false);val('lanInterface',l.interface||'auto');val('lanConnection',l.connection||'PowerGateway-LAN');val('lanAddress',l.address);val('lanGateway',l.gateway);val('lanDns',(l.dns||[]).join(', '));chk('wifiEnabled',w.enabled);val('wifiInterface',w.interface||'auto');val('wifiConnection',w.connection||'PowerGateway-WLAN');val('wifiSsid',w.ssid);val('wifiPassword','');chk('lteEnabled',m.enabled);val('lteConnection',m.connection||'PowerGateway-LTE');val('lteApn',m.apn);val('lteUsername',m.username);val('ltePassword','');val('ltePin','');val('hotspotMode',h.mode||'auto');val('hotspotInterface',h.interface||'wlan0');val('hotspotSsid',h.ssid||'PowerGateway-Setup');val('hotspotPassword','');val('hotspotAddress',h.address||'192.168.50.1/24');chk('hotspotOffline',h.offline_fallback!==false);$('networkCards').innerHTML=[card('Aktiv',(s.active||'keine').toUpperCase(),s.online?'ok':'bad'),card('LAN',s.lan?.state||'unbekannt'),card('WLAN',s.wifi?.state||'unbekannt'),card('LTE',s.lte?.state||'unbekannt'),card('Hotspot',s.hotspot_active?'Aktiv':'Inaktiv',s.hotspot_active?'warn':'')].join('')}catch(e){notice(e.message,false)}}
async function scanWifi(){try{$('wifiList').textContent='Suche läuft …';const d=await api('/_internal/network/wifi-scan');$('wifiList').innerHTML=d.networks?.length?d.networks.map(n=>`<div class="status-row"><strong>${esc(n.ssid)}</strong><span>${n.signal}% · ${esc(n.security)}</span><button class="secondary" onclick="val('wifiSsid',${JSON.stringify(n.ssid)})">Auswählen</button></div>`).join(''):'Keine WLANs gefunden.'}catch(e){$('wifiList').textContent=e.message}}
async function saveNetwork(){const priority=[$('prio1').value,$('prio2').value,$('prio3').value];if(new Set(priority).size!==3){notice('Jede Priorität darf nur einmal verwendet werden.',false);return}const body={priority,lan:{enabled:$('lanEnabled').checked,interface:$('lanInterface').value,connection:$('lanConnection').value,dhcp:$('lanDhcp').checked,address:$('lanAddress').value,gateway:$('lanGateway').value,dns:$('lanDns').value.split(',').map(x=>x.trim()).filter(Boolean)},wifi:{enabled:$('wifiEnabled').checked,interface:$('wifiInterface').value,connection:$('wifiConnection').value,ssid:$('wifiSsid').value,password:$('wifiPassword').value},lte:{enabled:$('lteEnabled').checked,connection:$('lteConnection').value,apn:$('lteApn').value,username:$('lteUsername').value,password:$('ltePassword').value,pin:$('ltePin').value},hotspot:{mode:$('hotspotMode').value,interface:$('hotspotInterface').value,connection:'PowerGateway-Setup',ssid:$('hotspotSsid').value,password:$('hotspotPassword').value,address:$('hotspotAddress').value,offline_fallback:$('hotspotOffline').checked}};try{const d=await api('/_internal/network',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});notice(d.message);setTimeout(loadNetwork,2500)}catch(e){notice(e.message,false)}}
async function loadUsers(){try{const d=await api('/_internal/users');$('userList').innerHTML=d.users.map(u=>`<div class="status-row"><strong>${esc(u.username)}</strong><span>${esc(u.role)} · ${u.enabled?'aktiv':'gesperrt'}</span></div>`).join('')}catch(e){notice(e.message,false)}}
async function changePassword(){if($('newPassword').value!==$('newPassword2').value){notice('Die neuen Passwörter stimmen nicht überein.',false);return}try{const d=await api('/_internal/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old_password:$('oldPassword').value,new_password:$('newPassword').value})});notice(d.message);['oldPassword','newPassword','newPassword2'].forEach(x=>val(x,''))}catch(e){notice(e.message,false)}}
async function loadDiagnostics(){try{$('diagnosticOutput').textContent='Diagnose läuft …';const d=await api('/_internal/diagnostics');$('diagnosticOutput').textContent=d.output||'Keine Ausgabe'}catch(e){$('diagnosticOutput').textContent=e.message}}
refresh();setInterval(refresh,5000);
</script></body></html>""".replace("__STYLE__", STYLE)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def base_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, ValueError):
        return {}


def settings() -> dict[str, Any]:
    return read_json(SETTINGS_PATH)


def default_network() -> dict[str, Any]:
    return {"priority":["lan","wifi","lte"],"lan":{"enabled":True,"interface":"auto","connection":"PowerGateway-LAN","dhcp":True,"address":"","gateway":"","dns":[]},"wifi":{"enabled":True,"interface":"auto","connection":"PowerGateway-WLAN","ssid":"","password":""},"lte":{"enabled":False,"connection":"PowerGateway-LTE","apn":"","username":"","password":"","pin":""},"hotspot":{"mode":"auto","interface":"wlan0","connection":"PowerGateway-Setup","ssid":"PowerGateway-Setup","password":"powergateway","address":"192.168.50.1/24","offline_fallback":True}}


def network_config(include_secrets: bool = False) -> dict[str, Any]:
    config = default_network()
    stored = read_json(NETWORK_CONFIG_PATH) or base_config().get("network", {})
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    if not include_secrets:
        for section in ("wifi", "lte", "hotspot"):
            for key in ("password", "pin"):
                config.get(section, {}).pop(key, None)
    return config


def login_required(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not has_users(USERS_PATH):
            return redirect(url_for("setup_page"))
        if not session.get("username"):
            if request.path.startswith("/_internal/"):
                return jsonify({"error": "Anmeldung erforderlich"}), 401
            return redirect(url_for("login_page"))
        return function(*args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"
    return response


@app.route("/setup", methods=["GET", "POST"])
def setup_page() -> Any:
    if has_users(USERS_PATH):
        return redirect(url_for("login_page"))
    error = None
    gateway_name = request.form.get("gateway_name", "PowerGateway")
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if password != request.form.get("password_confirm", ""):
            error = "Die Passwörter stimmen nicht überein."
        else:
            try:
                create_user(USERS_PATH, username, password, "admin")
                atomic_json(SETTINGS_PATH, {"gateway_name": gateway_name.strip() or "PowerGateway", "setup_complete": True})
                session.clear(); session["username"] = username.strip().lower(); session["role"] = "admin"; session.permanent = True
                return redirect(url_for("index"))
            except ValueError as exc:
                error = str(exc)
    return render_template_string(SETUP_PAGE, error=error, gateway_name=gateway_name)


@app.route("/login", methods=["GET", "POST"])
def login_page() -> Any:
    if not has_users(USERS_PATH):
        return redirect(url_for("setup_page"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        record = verify_user(USERS_PATH, username, request.form.get("password", ""))
        if record:
            session.clear(); session["username"] = username; session["role"] = record.get("role", "user"); session.permanent = True
            return redirect(url_for("index"))
        error = "Benutzername oder Passwort ist falsch."
    return render_template_string(LOGIN_PAGE, error=error)


@app.get("/logout")
def logout() -> Any:
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/")
@login_required
def index() -> str:
    return render_template_string(PAGE)


@app.get("/health")
def health() -> Response:
    return jsonify({"status": "ok", "setup_complete": has_users(USERS_PATH)})


@app.get("/_internal/overview")
@login_required
def overview() -> Response:
    config = base_config(); status = read_json(DATA_DIR / "status.json"); values = read_json(DATA_DIR / "latest_values.json")
    timestamp_value = values.get("received_at") or status.get("last_telegram_at")
    try:
        timestamp = datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00")) if timestamp_value else None
        age = max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()) if timestamp else None
    except ValueError:
        age = None
    gateway_name = settings().get("gateway_name") or config.get("gateway", {}).get("name", "PowerGateway")
    return jsonify({"version":VERSION_PATH.read_text(encoding="utf-8").strip() if VERSION_PATH.exists() else "unbekannt","gateway_name":gateway_name,"status":status,"values":values,"network":read_json(NETWORK_STATUS_PATH),"last_telegram_age_seconds":age,"current_user":session.get("username")})


@app.get("/_internal/network")
@login_required
def get_network() -> Response:
    return jsonify({"config":network_config(False),"status":read_json(NETWORK_STATUS_PATH),"result":read_json(NETWORK_RESULT_PATH)})


@app.post("/_internal/network")
@login_required
def set_network() -> Response:
    supplied = request.get_json(silent=True)
    if not isinstance(supplied, dict): return jsonify({"error":"Ungültige Konfiguration"}),400
    current = network_config(True)
    for section in ("wifi","lte","hotspot"):
        incoming = supplied.get(section,{})
        if isinstance(incoming,dict):
            for secret in ("password","pin"):
                if not incoming.get(secret) and current.get(section,{}).get(secret): incoming[secret]=current[section][secret]
    priority = supplied.get("priority",[])
    if sorted(priority) != ["lan","lte","wifi"]: return jsonify({"error":"Ungültige Netzwerkpriorität"}),400
    hotspot_password = str(supplied.get("hotspot",{}).get("password",""))
    if supplied.get("hotspot",{}).get("mode") != "off" and len(hotspot_password) < 8: return jsonify({"error":"Das Hotspot-Passwort muss mindestens 8 Zeichen haben"}),400
    atomic_json(NETWORK_CONFIG_PATH,supplied)
    return jsonify({"ok":True,"message":"Netzwerkkonfiguration gespeichert. Die Anwendung erfolgt innerhalb weniger Sekunden."})


@app.get("/_internal/network/wifi-scan")
@login_required
def scan_networks() -> Response:
    return jsonify({"networks":wifi_scan(str(network_config(False).get("wifi",{}).get("interface","")))})


@app.get("/_internal/users")
@login_required
def users() -> Response:
    return jsonify({"users":list_users(USERS_PATH)})


@app.post("/_internal/password")
@login_required
def password() -> Response:
    supplied = request.get_json(silent=True) or {}
    username = str(session.get("username", ""))
    if not verify_user(USERS_PATH, username, str(supplied.get("old_password", ""))):
        return jsonify({"error":"Das aktuelle Passwort ist falsch."}),400
    try:
        change_password(USERS_PATH, username, str(supplied.get("new_password", "")))
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400
    return jsonify({"ok":True,"message":"Passwort wurde geändert."})


@app.get("/_internal/diagnostics")
@login_required
def diagnostics() -> Response:
    commands=(("PowerGateway",["systemctl","is-active","powergateway"]),("Weboberfläche",["systemctl","is-active","powergateway-web"]),("Netzwerk",["systemctl","is-active","powergateway-network"]),("Netzwerkgeräte",["nmcli","device","status"]),("LTE-Modem",["mmcli","-L"]),("WireGuard",["wg","show"]))
    parts=[]
    for title,command in commands:
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False); output=(result.stdout+result.stderr).strip() or f"Keine Ausgabe (Exit-Code {result.returncode})"
        except (OSError,subprocess.TimeoutExpired) as exc: output=str(exc)
        parts.append(f"## {title}\n$ {' '.join(command)}\n{output}")
    return jsonify({"output":"\n\n".join(parts)})


if __name__ == "__main__":
    web=base_config().get("web",{})
    app.run(host=str(web.get("host","0.0.0.0")),port=int(web.get("port",8080)),debug=False)
