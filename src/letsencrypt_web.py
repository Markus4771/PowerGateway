#!/usr/bin/env python3
"""WebGUI und API für Let's-Encrypt-Zertifikate."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from flask import Response, jsonify, request

import ssh_tunnel_web as previous

app = previous.app
legacy = previous.legacy
runtime = previous.runtime
CONF = Path('/etc/powergateway/letsencrypt.conf')
CERT = Path('/etc/powergateway/tls/powergateway.crt')
HELPER = '/usr/local/sbin/powergateway-certbot'
DOMAIN_RE = re.compile(r'^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args, 124, exc.stdout or '', 'Zeitüberschreitung')
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, '', str(exc))


def _configured() -> dict[str, str]:
    result = {'domain': '', 'email': ''}
    try:
        for line in CONF.read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            value = value.strip().strip("'").strip('"')
            if key == 'DOMAIN': result['domain'] = value
            if key == 'EMAIL': result['email'] = value
    except OSError:
        pass
    return result


def _certificate() -> dict:
    result = {'present': CERT.exists(), 'issuer': '', 'subject': '', 'not_before': '', 'not_after': '', 'days_remaining': None}
    if not CERT.exists():
        return result
    proc = _run(['/usr/bin/openssl', 'x509', '-in', str(CERT), '-noout', '-issuer', '-subject', '-startdate', '-enddate'], 10)
    if proc.returncode != 0:
        result['error'] = proc.stderr.strip()
        return result
    for line in proc.stdout.splitlines():
        key, _, value = line.partition('=')
        if key == 'issuer': result['issuer'] = value.strip()
        elif key == 'subject': result['subject'] = value.strip()
        elif key == 'notBefore': result['not_before'] = value.strip()
        elif key == 'notAfter':
            result['not_after'] = value.strip()
            try:
                expiry = datetime.strptime(value.strip(), '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
                result['days_remaining'] = max(0, (expiry - datetime.now(timezone.utc)).days)
            except ValueError:
                pass
    result['letsencrypt'] = "Let's Encrypt" in result['issuer']
    return result


@app.get('/_internal/letsencrypt')
@legacy.login_required
def letsencrypt_status() -> Response:
    timer = _run(['/usr/bin/systemctl', 'is-enabled', 'certbot.timer'], 5)
    active = _run(['/usr/bin/systemctl', 'is-active', 'certbot.timer'], 5)
    return jsonify({'config': _configured(), 'certificate': _certificate(), 'timer_enabled': timer.stdout.strip() == 'enabled', 'timer_active': active.stdout.strip() == 'active'})


@app.post('/_internal/letsencrypt/issue')
@legacy.login_required
def letsencrypt_issue() -> Response:
    data = request.get_json(silent=True) or {}
    domain = str(data.get('domain', '')).strip().lower()
    email = str(data.get('email', '')).strip()
    if not DOMAIN_RE.fullmatch(domain):
        return jsonify({'ok': False, 'message': 'Bitte einen gültigen vollständigen Domainnamen eingeben.'}), 400
    if not EMAIL_RE.fullmatch(email):
        return jsonify({'ok': False, 'message': 'Bitte eine gültige E-Mail-Adresse eingeben.'}), 400
    proc = _run(['sudo', '-n', HELPER, 'issue', domain, email])
    message = proc.stderr.strip() or proc.stdout.strip() or 'Zertifikat wurde angefordert.'
    return jsonify({'ok': proc.returncode == 0, 'message': message, 'certificate': _certificate()}), 200 if proc.returncode == 0 else 500


@app.post('/_internal/letsencrypt/renew')
@legacy.login_required
def letsencrypt_renew() -> Response:
    proc = _run(['sudo', '-n', HELPER, 'renew'])
    message = proc.stderr.strip() or proc.stdout.strip() or 'Zertifikatsverlängerung wurde geprüft.'
    return jsonify({'ok': proc.returncode == 0, 'message': message, 'certificate': _certificate()}), 200 if proc.returncode == 0 else 500


SECTION = r'''
<section id="httpsSecurity" class="tab"><div class="toolbar"><div><h2>HTTPS & Let's Encrypt</h2><div class="muted">Öffentlich vertrauenswürdiges Zertifikat automatisch ausstellen und verlängern.</div></div><button onclick="loadLetsEncrypt()">Neu laden</button></div>
<div class="section two"><div class="card"><h2>Let's Encrypt einrichten</h2><div class="form-grid"><div class="field full"><label>Vollständiger Domainname</label><input id="leDomain" placeholder="powergateway.example.de"></div><div class="field full"><label>E-Mail-Adresse</label><input id="leEmail" type="email" placeholder="admin@example.de"></div><div class="field full"><button onclick="issueLetsEncrypt()">Zertifikat anfordern</button> <button class="secondary" onclick="renewLetsEncrypt()">Verlängerung jetzt prüfen</button></div></div><pre id="leResult">Noch nicht geprüft.</pre></div>
<div class="card"><h2>Voraussetzungen</h2><div class="status-row"><span>DNS</span><strong>Domain zeigt auf den Internetanschluss</strong></div><div class="status-row"><span>Port 80/TCP</span><strong>Von außen zum PowerGateway weiterleiten</strong></div><div class="status-row"><span>Port 443/TCP</span><strong>Für die HTTPS-Weboberfläche</strong></div><p class="muted">Die HTTP-01-Prüfung verwendet ausschließlich <code>/.well-known/acme-challenge/</code>. Nach erfolgreicher Ausstellung wird nginx automatisch neu geladen.</p><p class="muted">Bei DS-Lite oder ohne eingehende Erreichbarkeit ist später eine DNS-01-Erweiterung erforderlich.</p></div></div>
<div class="section"><div class="card"><h2>Zertifikatsstatus</h2><div id="leStatus" class="muted">Noch nicht geladen.</div></div></div></section>
'''
JS = r'''
function showLeStatus(d){const c=d.certificate||{},cfg=d.config||{};$('leStatus').innerHTML=`<div class="status-row"><span>Typ</span><strong>${c.letsencrypt?'Let\'s Encrypt':(c.present?'Lokales/eigenes Zertifikat':'Kein Zertifikat')}</strong></div><div class="status-row"><span>Domain</span><strong>${esc(cfg.domain||'—')}</strong></div><div class="status-row"><span>Aussteller</span><strong>${esc(c.issuer||'—')}</strong></div><div class="status-row"><span>Gültig bis</span><strong>${esc(c.not_after||'—')}</strong></div><div class="status-row"><span>Restlaufzeit</span><strong>${c.days_remaining===null?'—':esc(c.days_remaining+' Tage')}</strong></div><div class="status-row"><span>Automatische Verlängerung</span><strong>${d.timer_enabled&&d.timer_active?'Aktiv':'Nicht aktiv'}</strong></div>`}
async function loadLetsEncrypt(){try{const d=await api('/_internal/letsencrypt');val('leDomain',(d.config||{}).domain||'');val('leEmail',(d.config||{}).email||'');showLeStatus(d)}catch(e){notice(e.message,false)}}
async function issueLetsEncrypt(){try{const d=await api('/_internal/letsencrypt/issue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({domain:$('leDomain').value.trim(),email:$('leEmail').value.trim()})});$('leResult').textContent=d.message;notice(d.message,d.ok!==false);await loadLetsEncrypt()}catch(e){$('leResult').textContent=e.message;notice(e.message,false)}}
async function renewLetsEncrypt(){try{const d=await api('/_internal/letsencrypt/renew',{method:'POST'});$('leResult').textContent=d.message;notice(d.message,d.ok!==false);await loadLetsEncrypt()}catch(e){$('leResult').textContent=e.message;notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'httpsSecurity\',this)">HTTPS</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users"', SECTION + '<section id="users"')
page = page.replace("if(id==='users')loadUsers();", "if(id==='httpsSecurity')loadLetsEncrypt();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
legacy.PAGE = page
