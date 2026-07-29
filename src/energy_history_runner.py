#!/usr/bin/env python3
"""Robuster One-shot-Sammler für die PowerGateway-Energiehistorie.

Die Datenbank wird bei jedem Lauf initialisiert. Fehlende Zählerwerte sind
kein Dienstfehler, sondern ein normaler Wartezustand.
"""
from __future__ import annotations

import json

import energy_history


def main() -> int:
    # Datenbank und Schema immer anlegen, auch bevor der erste Messwert da ist.
    with energy_history._connect():
        pass

    result = energy_history.sample()
    if not result.get("ok"):
        result = {
            "ok": True,
            "status": "waiting",
            "message": "Noch keine Messwerte vorhanden. Warte auf erste Zählerdaten.",
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
