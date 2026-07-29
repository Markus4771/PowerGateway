#!/usr/bin/env python3
"""Integriertes Backup-Center für PowerGateway.

Erstellt prüfbare .pgbackup-Dateien mit Manifest und SHA-256-Prüfsummen.
Die Weboberfläche kann Sicherungen erzeugen, prüfen, herunterladen und löschen.
Eine Wiederherstellung wird aus Sicherheitsgründen zunächst in einen Staging-
Ordner entpackt; die endgültige Übernahme erfolgt über den mitgelieferten
Root-Befehl backup_restore.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request, send_file

import energy_history

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime

BACKUP_DIR = Path('/var/lib/powergateway/backups')
STAGING_DIR = Path('/var/lib/powergateway/restore-staging')
SETTINGS_FILE = Path('/var/lib/powergateway/backup_settings.json')
VERSION_FILE = Path('/opt/powergateway/version.txt')
SOURCE_PATHS = (
    Path('/etc/powergateway'),
    Path('/var/lib/powergateway'),
)
EXCLUDED_PARTS = {'backups', 'restore-staging', 'exports', '__pycache__'}


def _version() -> str:
    try:
        return VERSION_FILE.read_text(encoding='utf-8').strip() or 'unbekannt'
    except OSError:
        return 'unbekannt'


def _safe_name(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('._')
    return value[:160] or 'PowerGateway_Backup.pgbackup'


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iter_source_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for root in SOURCE_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            files.append((root, root.as_posix().lstrip('/')))
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                relative_parts = path.relative_to(root).parts
            except ValueError:
                continue
            if any(part in EXCLUDED_PARTS for part in relative_parts):
                continue
            archive_name = path.as_posix().lstrip('/')
            files.append((path, archive_name))
    return files


def create_backup(comment: str = '', include_logs: bool = False) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S')
    filename = _safe_name(f'PowerGateway_{_version()}_{stamp}.pgbackup')
    target = BACKUP_DIR / filename
    temporary = target.with_suffix(target.suffix + '.tmp')
    entries: list[dict[str, Any]] = []

    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for source, archive_name in _iter_source_files():
            try:
                data = source.read_bytes()
                stat = source.stat()
            except OSError:
                continue
            archive.writestr(archive_name, data)
            entries.append({
                'path': archive_name,
                'size': len(data),
                'sha256': _sha256_bytes(data),
                'mode': oct(stat.st_mode & 0o777),
                'mtime': int(stat.st_mtime),
            })
        if include_logs:
            info = b'Logexport ist in dieser Version vorbereitet; Journaldaten werden nicht automatisch in Backups aufgenommen.\n'
            archive.writestr('metadata/logs-info.txt', info)
            entries.append({'path': 'metadata/logs-info.txt', 'size': len(info), 'sha256': _sha256_bytes(info), 'mode': '0o640', 'mtime': int(time.time())})
        manifest = {
            'format': 'PowerGateway Backup',
            'format_version': 1,
            'product_version': _version(),
            'created_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'hostname': os.uname().nodename,
            'comment': str(comment or '')[:500],
            'components': ['configuration', 'application-data', 'energy-history', 'network', 'mqtt', 'wireguard', 'users'],
            'files': entries,
        }
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    temporary.replace(target)
    cleanup_backups()
    return target


def verify_backup(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path, 'r') as archive:
            bad = archive.testzip()
            if bad:
                errors.append(f'Beschädigter ZIP-Eintrag: {bad}')
            try:
                manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
            except Exception as exc:
                return {'ok': False, 'errors': [f'Manifest fehlt oder ist ungültig: {exc}']}
            names = set(archive.namelist())
            for item in manifest.get('files', []):
                name = str(item.get('path', ''))
                if name not in names:
                    errors.append(f'Datei fehlt: {name}')
                    continue
                data = archive.read(name)
                if _sha256_bytes(data) != item.get('sha256'):
                    errors.append(f'Prüfsumme stimmt nicht: {name}')
            return {'ok': not errors, 'errors': errors, 'manifest': manifest}
    except (OSError, zipfile.BadZipFile) as exc:
        return {'ok': False, 'errors': [str(exc)]}


def _settings() -> dict[str, Any]:
    defaults = {'schedule': 'off', 'retention_count': 10, 'retention_mb': 1024}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            defaults.update(data)
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    schedule = str(data.get('schedule', 'off'))
    if schedule not in {'off', 'daily', 'weekly', 'monthly'}:
        schedule = 'off'
    settings = {
        'schedule': schedule,
        'retention_count': max(1, min(100, int(data.get('retention_count', 10)))),
        'retention_mb': max(50, min(10240, int(data.get('retention_mb', 1024)))),
    }
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    cleanup_backups(settings)
    return settings


def cleanup_backups(settings: dict[str, Any] | None = None) -> None:
    settings = settings or _settings()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in BACKUP_DIR.glob('*.pgbackup') if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    keep_count = int(settings.get('retention_count', 10))
    max_bytes = int(settings.get('retention_mb', 1024)) * 1024 * 1024
    total = 0
    for index, path in enumerate(files):
        size = path.stat().st_size
        total += size
        if index >= keep_count or total > max_bytes:
            try:
                path.unlink()
            except OSError:
                pass


def _resolved(name: str) -> Path | None:
    path = BACKUP_DIR / _safe_name(name)
    try:
        if path.is_file() and path.resolve().parent == BACKUP_DIR.resolve():
            return path
    except OSError:
        pass
    return None


@app.post('/_internal/backup/create')
@legacy.login_required
def backup_create() -> Response:
    data = request.get_json(silent=True) or {}
    try:
        path = create_backup(str(data.get('comment', '')), bool(data.get('include_logs', False)))
        return jsonify({'ok': True, 'filename': path.name, 'size': path.stat().st_size, 'download_url': '/_internal/backup/download/' + path.name})
    except Exception as exc:
        return jsonify({'ok': False, 'error': f'Backup konnte nicht erstellt werden: {exc}'}), 500


@app.get('/_internal/backup/list')
@legacy.login_required
def backup_list() -> Response:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(BACKUP_DIR.glob('*.pgbackup'), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        files.append({'name': path.name, 'size': stat.st_size, 'created': int(stat.st_mtime), 'download_url': '/_internal/backup/download/' + path.name})
    return jsonify({'ok': True, 'files': files, 'total_size': sum(f['size'] for f in files), 'settings': _settings()})


@app.get('/_internal/backup/download/<name>')
@legacy.login_required
def backup_download(name: str):
    path = _resolved(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden.'}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.post('/_internal/backup/verify/<name>')
@legacy.login_required
def backup_verify(name: str) -> Response:
    path = _resolved(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden.'}), 404
    result = verify_backup(path)
    return jsonify(result), (200 if result.get('ok') else 422)


@app.post('/_internal/backup/stage/<name>')
@legacy.login_required
def backup_stage(name: str) -> Response:
    path = _resolved(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden.'}), 404
    checked = verify_backup(path)
    if not checked.get('ok'):
        return jsonify(checked), 422
    target = STAGING_DIR / _safe_name(path.stem)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'r') as archive:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if target.resolve() not in destination.parents and destination != target.resolve():
                return jsonify({'ok': False, 'error': 'Unsicherer Dateipfad im Backup.'}), 422
        archive.extractall(target)
    command = f"sudo /opt/powergateway/src/backup_restore.py '{target}'"
    return jsonify({'ok': True, 'staging_path': str(target), 'command': command, 'message': 'Backup geprüft und zur Wiederherstellung vorbereitet.'})


@app.delete('/_internal/backup/<name>')
@legacy.login_required
def backup_delete(name: str) -> Response:
    path = _resolved(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden.'}), 404
    path.unlink()
    return jsonify({'ok': True})


@app.get('/_internal/backup/settings')
@legacy.login_required
def backup_settings_get() -> Response:
    return jsonify({'ok': True, 'settings': _settings()})


@app.post('/_internal/backup/settings')
@legacy.login_required
def backup_settings_post() -> Response:
    try:
        return jsonify({'ok': True, 'settings': save_settings(request.get_json(silent=True) or {})})
    except (TypeError, ValueError) as exc:
        return jsonify({'ok': False, 'error': f'Ungültige Einstellungen: {exc}'}), 400


SECTION = r'''
<section id="backups" class="tab"><div class="toolbar"><div><h2>Backup & Wiederherstellung</h2><div class="muted">Konfiguration und Anwendungsdaten sichern, prüfen und für eine Wiederherstellung vorbereiten.</div></div><button class="secondary" onclick="loadBackups()">Archiv aktualisieren</button></div><div class="section backup-form"><div class="form-grid"><label>Kommentar<input id="backupComment" maxlength="500" placeholder="z. B. vor Systemupdate"></label><label>Zeitplan<select id="backupSchedule"><option value="off">Aus</option><option value="daily">Täglich</option><option value="weekly">Wöchentlich</option><option value="monthly">Monatlich</option></select></label><label>Aufbewahrung (Anzahl)<input id="backupRetention" type="number" min="1" max="100" value="10"></label><label>Maximaler Speicher (MB)<input id="backupRetentionMb" type="number" min="50" max="10240" value="1024"></label></div><div class="backup-actions"><button id="backupCreateButton" onclick="createBackup()">Backup erstellen</button><button class="secondary" onclick="saveBackupSettings()">Zeitplan speichern</button><span class="muted" id="backupProgress"></span></div></div><div class="section"><div class="toolbar"><div><h3>Backup-Archiv</h3><div class="muted" id="backupArchiveInfo">Noch nicht geladen.</div></div></div><div class="table-wrap"><table><thead><tr><th>Datei</th><th>Erstellt</th><th>Größe</th><th>Aktionen</th></tr></thead><tbody id="backupRows"><tr><td colspan="4" class="muted">Noch keine Backups geladen.</td></tr></tbody></table></div></div></section>
'''
STYLE = r'''
.backup-form{max-width:950px}.backup-actions{display:flex;gap:12px;align-items:center;margin-top:16px;flex-wrap:wrap}.backup-file{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88rem}.backup-actions-cell{display:flex;gap:7px;flex-wrap:wrap}.backup-actions-cell .danger{background:#fff0ee;color:var(--bad)}@media(max-width:600px){.backup-actions{align-items:stretch;flex-direction:column}.backup-actions button{width:100%}}
'''
JS = r'''
function backupSize(bytes){const u=['B','KB','MB','GB'];let n=Number(bytes)||0,i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return n.toLocaleString('de-DE',{maximumFractionDigits:1})+' '+u[i]}
async function loadBackups(){try{const d=await api('/_internal/backup/list');const s=d.settings||{};$('backupSchedule').value=s.schedule||'off';$('backupRetention').value=s.retention_count||10;$('backupRetentionMb').value=s.retention_mb||1024;$('backupArchiveInfo').textContent=(d.files||[]).length+' Dateien · '+backupSize(d.total_size);$('backupRows').innerHTML=(d.files||[]).length?(d.files||[]).map(f=>`<tr><td class="backup-file">${esc(f.name)}</td><td>${new Date(f.created*1000).toLocaleString('de-DE')}</td><td>${backupSize(f.size)}</td><td><div class="backup-actions-cell"><a class="button secondary" href="${f.download_url}">Download</a><button class="secondary" onclick="verifyBackup('${encodeURIComponent(f.name)}')">Prüfen</button><button class="secondary" onclick="stageBackup('${encodeURIComponent(f.name)}')">Wiederherstellung</button><button class="danger" onclick="deleteBackup('${encodeURIComponent(f.name)}')">Löschen</button></div></td></tr>`).join(''):'<tr><td colspan="4" class="muted">Noch keine Backups vorhanden.</td></tr>'}catch(e){notice(e.message,false)}}
async function createBackup(){const b=$('backupCreateButton');b.disabled=true;$('backupProgress').textContent='Backup wird erstellt …';try{const d=await api('/_internal/backup/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({comment:$('backupComment').value})});$('backupProgress').innerHTML=`Fertig: <a href="${d.download_url}">${esc(d.filename)}</a> (${backupSize(d.size)})`;notice('Backup wurde erstellt.',true);await loadBackups()}catch(e){$('backupProgress').textContent='';notice(e.message,false)}finally{b.disabled=false}}
async function saveBackupSettings(){try{await api('/_internal/backup/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schedule:$('backupSchedule').value,retention_count:Number($('backupRetention').value),retention_mb:Number($('backupRetentionMb').value)})});notice('Backup-Einstellungen gespeichert.',true)}catch(e){notice(e.message,false)}}
async function verifyBackup(encoded){try{const d=await api('/_internal/backup/verify/'+encoded,{method:'POST'});notice('Backup ist vollständig und die Prüfsummen stimmen.',true)}catch(e){notice(e.message,false)}}
async function stageBackup(encoded){if(!confirm('Backup prüfen und zur Wiederherstellung vorbereiten? Das laufende System wird noch nicht verändert.'))return;try{const d=await api('/_internal/backup/stage/'+encoded,{method:'POST'});prompt('Backup wurde vorbereitet. Diesen Befehl per SSH ausführen:',d.command);notice(d.message,true)}catch(e){notice(e.message,false)}}
async function deleteBackup(encoded){if(!confirm('Backup wirklich löschen?'))return;try{await api('/_internal/backup/'+encoded,{method:'DELETE'});notice('Backup gelöscht.',true);await loadBackups()}catch(e){notice(e.message,false)}}
'''
page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'backups\',this)">Backup & Restore</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users" class="tab">', SECTION + '<section id="users" class="tab">')
page = page.replace("if(id==='users')loadUsers();", "if(id==='backups')loadBackups();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
energy_history.legacy.PAGE = page
