#!/usr/bin/env python3
"""Fehlertolerantes Laden optionaler Energie-Erweiterungen.

Die Kern-WebGUI darf nicht ausfallen, wenn ein Analyse- oder Darstellungsmodul
nicht importiert werden kann. Kompatibilitaetsattribute werden zentral gesetzt
und Importfehler fuer die Moduldiagnose protokolliert.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

import energy_history
import energy_chart_phase2

LOGGER = logging.getLogger(__name__)
LOAD_RESULTS: dict[str, dict[str, Any]] = {}

# Abwaertskompatibilitaet fuer Module, die Phase 2 als vorherige Schicht nutzen.
energy_chart_phase2.app = energy_history.app
energy_chart_phase2.legacy = energy_history.legacy
energy_chart_phase2.runtime = energy_history.runtime


def load_optional(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
        LOAD_RESULTS[module_name] = {'ok': True}
    except Exception as exc:  # Die Kern-WebGUI muss trotzdem starten.
        LOAD_RESULTS[module_name] = {
            'ok': False,
            'error': f'{type(exc).__name__}: {exc}',
        }
        LOGGER.exception('Optionales PowerGateway-Modul %s konnte nicht geladen werden', module_name)


# Der Renderer-Fallback wird bewusst zuletzt geladen. Dadurch überschreibt er
# keine Daten- oder Analysefunktionen, stellt aber renderEnergyChart immer bereit.
for _module in (
    'energy_analysis_phase3',
    'energy_adaptive_phase4',
    'energy_chart_runtime_fix',
):
    load_optional(_module)
