#!/usr/bin/env python3
"""Erweiterungen des Backup-Centers für PowerGateway 1.3.8-dev.

Ergänzt sicheren Upload, Vorschau, Audit-Protokoll und eine detailliertere
Archivübersicht, ohne die bestehende Backup-Implementierung zu duplizieren.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import backup_center

app = backup_center.app
legacy = backup_center.legacy
runtime = backup_center.runtime

AUDIT_FILE = Path('/var/lib/powergateway/backup_audit.jsonl')
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
ALLOWED_SUFFIX = '.pgbackup'


def _audit(action: str, ok: bool, **details: Any) -> None:
    """Schreibt einen begrenzten, zeilenbasierten Audit-Eintrag."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'timestamp': datetime.now().astimezone().isoformat(timespec='seconds'),
        'action': action,
        'ok': bool(ok),
        'details': details,
    }
    try:
        with AUDIT_FILE.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        # Begrenzung auf die letzten 500 Einträge.
        lines = AUDIT_FILE.read_text(encoding='utf-8').splitlines()
        if len(lines) > 500:
            AUDIT_FILE.write_text('\n'.join(lines[-500:]) + '\n', encoding='utf-8')
    except OSError:
        pass


def _manifest_summary(result: dict[str, Any]) -> dict[str, Any]:
    manifest = result.get('manifest') if isinstance(result, dict) else None
    manifest = manifest if isinstance(manifest, dict) else {}
    files = manifest.get('files') if isinstance(manifest.get('files'), list) else []
    components = manifest.get('components') if isinstance(manifest.get('components'), list) else []
    return {
        'format': manifest.get('format', 'unbekannt'),
        'format_version': manifest.get('format_version'),
        'product_version': manifest.get('product_version', 'unbekannt'),
        'created_at': manifest.get('created_at'),
        'hostname': manifest.get('hostname'),
        'comment': manifest.get('comment', ''),
        'components': components,
        'file_count': len(files),
        'payload_size': sum(int(item.get('size', 0) or 0) for item in files if isinstance(item, dict)),
    }


@app.post('/_internal/backup/upload')
@legacy.login_required
def backup_upload() -> Response:
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return jsonify({'ok': False, 'error': 'Keine Backup-Datei ausgewählt.'}), 400

    filename = backup_center._safe_name(upload.filename)
    if not filename.lower().endswith(ALLOWED_SUFFIX):
        return jsonify({'ok': False, 'error': 'Es sind nur .pgbackup-Dateien erlaubt.'}), 400

    backup_center.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = backup_center.BACKUP_DIR / filename
    temporary = target.with_suffix(target.suffix + '.uploading')
    written = 0
    try:
        with temporary.open('wb') as handle:
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise ValueError('Die Datei ist größer als 512 MB.')
                handle.write(chunk)

        checked = backup_center.verify_backup(temporary)
        if not checked.get('ok'):
            _audit('upload', False, filename=filename, errors=checked.get('errors', []))
            temporary.unlink(missing_ok=True)
            return jsonify({'ok': False, 'error': 'Backup ist ungültig.', 'errors': checked.get('errors', [])}), 422

        if target.exists():
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            target = backup_center.BACKUP_DIR / f'{target.stem}_{stamp}{target.suffix}'
        temporary.replace(target)
        backup_center.cleanup_backups()
        summary = _manifest_summary(checked)
        _audit('upload', True, filename=target.name, size=written, product_version=summary['product_version'])
        return jsonify({'ok': True, 'filename': target.name, 'size': written, 'summary': summary})
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        _audit('upload', False, filename=filename, error=str(exc))
        return jsonify({'ok': False, 'error': f'Upload fehlgeschlagen: {exc}'}), 400


@app.get('/_internal/backup/preview/<name>')
@legacy.login_required
def backup_preview(name: str) -> Response:
    path = backup_center._resolved(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden.'}), 404
    checked = backup_center.verify_backup(path)
    summary = _manifest_summary(checked)
    _audit('preview', bool(checked.get('ok')), filename=path.name)
    return jsonify({
        'ok': bool(checked.get('ok')),
        'errors': checked.get('errors', []),
        'summary': summary,
        'archive_size': path.stat().st_size,
    }), (200 if checked.get('ok') else 422)


@app.get('/_internal/backup/audit')
@legacy.login_required
def backup_audit() -> Response:
    entries: list[dict[str, Any]] = []
    try:
        for line in AUDIT_FILE.read_text(encoding='utf-8').splitlines()[-100:]:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    entries.append(item)
            except ValueError:
                continue
    except OSError:
        pass
    return jsonify({'ok': True, 'entries': list(reversed(entries))})


@app.get('/_internal/backup/health')
@legacy.login_required
def backup_health() -> Response:
    settings = backup_center._settings()
    backup_center.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = list(backup_center.BACKUP_DIR.glob('*.pgbackup'))
    latest = max(files, key=lambda p: p.stat().st_mtime) if files else None
    writable = os.access(backup_center.BACKUP_DIR, os.W_OK)
    return jsonify({
        'ok': writable,
        'directory': str(backup_center.BACKUP_DIR),
        'writable': writable,
        'backup_count': len(files),
        'latest_backup': latest.name if latest else None,
        'latest_age_seconds': int(time.time() - latest.stat().st_mtime) if latest else None,
        'schedule': settings.get('schedule', 'off'),
        'retention_count': settings.get('retention_count', 10),
        'retention_mb': settings.get('retention_mb', 1024),
        'max_upload_mb': MAX_UPLOAD_BYTES // 1024 // 1024,
    })


EXTRA_STYLE = r'''
.backup-upload{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin-top:16px}.backup-upload label{min-width:280px;flex:1}.backup-preview{white-space:pre-wrap;max-height:260px;overflow:auto}.backup-health{margin-top:10px}
'''

EXTRA_HTML = r'''
<div class="backup-upload"><label>Backup importieren<input id="backupUploadFile" type="file" accept=".pgbackup,application/zip"></label><button class="secondary" onclick="uploadBackup()">Importieren und prüfen</button><button class="secondary" onclick="loadBackupHealth()">Status prüfen</button></div><div id="backupHealth" class="muted backup-health"></div>
'''

EXTRA_JS = r'''
async function uploadBackup(){const input=$('backupUploadFile');if(!input.files||!input.files[0]){notice('Bitte eine .pgbackup-Datei auswählen.',false);return}const form=new FormData();form.append('file',input.files[0]);try{const r=await fetch('/_internal/backup/upload',{method:'POST',body:form});const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.error||'Upload fehlgeschlagen');notice('Backup importiert und erfolgreich geprüft.',true);input.value='';await loadBackups()}catch(e){notice(e.message,false)}}
async function previewBackup(encoded){try{const d=await api('/_internal/backup/preview/'+encoded);const s=d.summary||{};alert('Backup-Vorschau\n\nVersion: '+(s.product_version||'unbekannt')+'\nErstellt: '+(s.created_at||'unbekannt')+'\nHost: '+(s.hostname||'unbekannt')+'\nDateien: '+(s.file_count||0)+'\nNutzdaten: '+backupSize(s.payload_size||0)+'\nKomponenten: '+((s.components||[]).join(', ')||'keine Angabe')+'\nKommentar: '+(s.comment||'–'))}catch(e){notice(e.message,false)}}
async function loadBackupHealth(){try{const d=await api('/_internal/backup/health');$('backupHealth').textContent=(d.writable?'Bereit':'Nicht beschreibbar')+' · '+d.backup_count+' Backups · Zeitplan: '+d.schedule+' · Upload-Limit: '+d.max_upload_mb+' MB'}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', EXTRA_STYLE + '</style></head>')
page = page.replace('<div class="backup-actions"><button id="backupCreateButton"', EXTRA_HTML + '<div class="backup-actions"><button id="backupCreateButton"')
page = page.replace('<button class="secondary" onclick="verifyBackup(\'${encodeURIComponent(f.name)}\')">Prüfen</button>', '<button class="secondary" onclick="previewBackup(\'${encodeURIComponent(f.name)}\')">Vorschau</button><button class="secondary" onclick="verifyBackup(\'${encodeURIComponent(f.name)}\')">Prüfen</button>')
page = page.replace('function backupSize(bytes)', EXTRA_JS + 'function backupSize(bytes)')
runtime.PAGE = page
backup_center.energy_history.legacy.PAGE = page
