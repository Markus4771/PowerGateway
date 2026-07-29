#!/usr/bin/env python3
"""Zeitgesteuerter PowerGateway-Backup-Lauf für systemd."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import backup_center

STATE_FILE = Path('/var/lib/powergateway/backup_state.json')


def _state() -> dict:
    try:
        value = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _due(schedule: str, now: datetime, last: datetime | None) -> bool:
    if schedule == 'off':
        return False
    if last is None:
        return True
    if schedule == 'daily':
        return last.date() < now.date()
    if schedule == 'weekly':
        return (now.date() - last.date()).days >= 7
    if schedule == 'monthly':
        return (last.year, last.month) != (now.year, now.month)
    return False


def main() -> int:
    settings = backup_center._settings()
    schedule = str(settings.get('schedule', 'off'))
    state = _state()
    last = None
    try:
        last = datetime.fromisoformat(str(state.get('last_success', '')))
    except ValueError:
        pass
    now = datetime.now().astimezone()
    if not _due(schedule, now, last):
        print(json.dumps({'ok': True, 'status': 'not-due', 'schedule': schedule}, ensure_ascii=False))
        return 0
    path = backup_center.create_backup(f'Automatisches {schedule}-Backup')
    STATE_FILE.write_text(json.dumps({'last_success': now.isoformat(timespec='seconds'), 'filename': path.name}, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'status': 'created', 'filename': path.name}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
