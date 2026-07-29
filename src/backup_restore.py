#!/usr/bin/env python3
"""Wendet ein zuvor geprüftes PowerGateway-Staging-Backup als root an."""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ALLOWED_ROOTS = (Path('/etc/powergateway'), Path('/var/lib/powergateway'))
STAGING_BASE = Path('/var/lib/powergateway/restore-staging').resolve()
ROLLBACK_BASE = Path('/var/lib/powergateway/restore-rollbacks')


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.rglob('*'):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_symlink():
            continue
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.restore-tmp')
            shutil.copy2(item, temporary)
            temporary.replace(destination)


def main() -> int:
    if os.geteuid() != 0:
        print('Fehler: Wiederherstellung muss mit sudo ausgeführt werden.', file=sys.stderr)
        return 2
    if len(sys.argv) != 2:
        print(f'Verwendung: sudo {sys.argv[0]} /var/lib/powergateway/restore-staging/<backup>', file=sys.stderr)
        return 2
    staging = Path(sys.argv[1]).resolve()
    if STAGING_BASE not in staging.parents or not staging.is_dir():
        print('Fehler: Ungültiger Staging-Pfad.', file=sys.stderr)
        return 2

    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    rollback = ROLLBACK_BASE / stamp
    rollback.mkdir(parents=True, exist_ok=True)

    for target in ALLOWED_ROOTS:
        staged_source = staging / target.as_posix().lstrip('/')
        if not staged_source.exists():
            continue
        current_backup = rollback / target.as_posix().lstrip('/')
        if target.exists():
            _copy_tree(target, current_backup)
        _copy_tree(staged_source, target)
        print(f'Wiederhergestellt: {target}')

    try:
        shutil.chown('/var/lib/powergateway', user='powergateway', group='powergateway')
    except (LookupError, OSError):
        pass
    print(f'Wiederherstellung abgeschlossen. Rollback: {rollback}')
    print('Bitte Dienste neu starten: systemctl restart powergateway.service powergateway-web.service')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
