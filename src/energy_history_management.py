#!/usr/bin/env python3
"""Gezieltes Loeschen historischer Energiedaten mit automatischer Sicherung."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import energy_history
import measurement_export

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime
DATA_DIR = Path('/var/lib/powergateway')
DB_FILE = DATA_DIR / 'energy_history.sqlite3'
JSONL_FILE = measurement_export.HISTORY_PATH
BACKUP_DIR = DATA_DIR / 'backups'


def _to_epoch(value: Any) -> int:
    text = str(value or '').strip()
    if not text:
        raise ValueError('Zeitpunkt fehlt.')
    parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int(parsed.timestamp())


def _record_epoch(record: dict[str, Any]) -> int | None:
    value = record.get('received_at') or record.get('captured_at')
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return int(parsed.timestamp())
    except ValueError:
        return None


def _backup_database(stamp: str) -> str | None:
    if not DB_FILE.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = BACKUP_DIR / f'energy_history-before-delete-{stamp}.sqlite3'
    with sqlite3.connect(DB_FILE, timeout=20) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return str(destination)


def _backup_jsonl(stamp: str) -> str | None:
    if not JSONL_FILE.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = BACKUP_DIR / f'measurement_history-before-delete-{stamp}.jsonl'
    shutil.copy2(JSONL_FILE, destination)
    return str(destination)


@app.post('/_internal/energy/history-delete')
@legacy.login_required
def energy_history_delete() -> Response:
    data = request.get_json(silent=True) or {}
    if data.get('confirmation') != 'HISTORIE LÖSCHEN':
        return jsonify({'ok': False, 'error': 'Bestätigung fehlt.'}), 400
    try:
        start = _to_epoch(data.get('start'))
        end = _to_epoch(data.get('end'))
    except (TypeError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    if end < start:
        start, end = end, start
    stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    db_backup = _backup_database(stamp)
    jsonl_backup = _backup_jsonl(stamp)

    deleted_db = 0
    if DB_FILE.exists():
        with sqlite3.connect(DB_FILE, timeout=20) as db:
            cursor = db.execute('DELETE FROM measurements WHERE ts BETWEEN ? AND ?', (start, end))
            deleted_db = max(0, int(cursor.rowcount or 0))
            db.commit()

    deleted_jsonl = 0
    kept: list[str] = []
    if JSONL_FILE.exists():
        with JSONL_FILE.open('r', encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    kept.append(line)
                    continue
                ts = _record_epoch(record)
                if ts is not None and start <= ts <= end:
                    deleted_jsonl += 1
                else:
                    kept.append(line)
        temporary = JSONL_FILE.with_suffix('.jsonl.tmp')
        temporary.write_text(''.join(kept), encoding='utf-8')
        temporary.replace(JSONL_FILE)

    return jsonify({
        'ok': True,
        'start': start,
        'end': end,
        'deleted_database_rows': deleted_db,
        'deleted_diagnostic_snapshots': deleted_jsonl,
        'database_backup': db_backup,
        'diagnostic_backup': jsonl_backup,
    })


UI = r'''
<div class="section card" id="energyHistoryDeletePanel">
  <h3>Historische Daten löschen</h3>
  <div class="muted">Löscht Messwerte nur im gewählten Zeitraum. Vorher wird automatisch eine Sicherung angelegt.</div>
  <div class="form-grid" style="margin-top:12px">
    <div class="field"><label>Von</label><input id="historyDeleteStart" type="datetime-local"></div>
    <div class="field"><label>Bis</label><input id="historyDeleteEnd" type="datetime-local"></div>
    <div class="field full"><button class="danger" type="button" onclick="deleteEnergyHistoryRange()">Gewählten Zeitraum löschen</button> <span id="historyDeleteResult" class="muted"></span></div>
  </div>
</div>
'''
SCRIPT = r'''
async function deleteEnergyHistoryRange(){
  const start=document.getElementById('historyDeleteStart')?.value||'';
  const end=document.getElementById('historyDeleteEnd')?.value||'';
  const out=document.getElementById('historyDeleteResult');
  if(!start||!end){if(out)out.textContent='Bitte Von und Bis auswählen.';return;}
  const typed=window.prompt('Zur Bestätigung HISTORIE LÖSCHEN eingeben:','');
  if(typed!=='HISTORIE LÖSCHEN'){if(out)out.textContent='Löschen abgebrochen.';return;}
  try{
    const d=await api('/_internal/energy/history-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:start,end:end,confirmation:typed})});
    if(out)out.textContent=`${d.deleted_database_rows||0} Historienwerte und ${d.deleted_diagnostic_snapshots||0} Diagnose-Snapshots gelöscht. Backup wurde angelegt.`;
    if(typeof loadEnergyHistory==='function')await loadEnergyHistory();
  }catch(e){if(out)out.textContent=e.message;notice(e.message,false)}
}
'''

page = runtime.PAGE
marker = '<div class="muted energy-reset-note">'
if marker in page:
    page = page.replace(marker, UI + marker, 1)
else:
    page = page.replace('</body>', UI + '</body>', 1)
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
runtime.PAGE = page
legacy.PAGE = page
