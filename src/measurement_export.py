#!/usr/bin/env python3
"""Begrenzter Diagnoseverlauf und CSV-Export für einzelne Messwerte.

Der Verlauf dient ausschließlich der Fehlersuche. Langzeitdaten und Diagramme
bleiben Aufgabe von Home Assistant beziehungsweise der vorhandenen Diagramm-Module.
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

import webapp_features as features

app = features.app
legacy = features.legacy
runtime = features.runtime

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA", "/var/lib/powergateway"))
LATEST_PATH = Path(os.environ.get("POWERGATEWAY_LATEST_VALUES", str(DATA_DIR / "latest_values.json")))
HISTORY_PATH = Path(os.environ.get("POWERGATEWAY_MEASUREMENT_HISTORY", str(DATA_DIR / "measurement_history.jsonl")))
MAX_SNAPSHOTS = max(100, int(os.environ.get("POWERGATEWAY_MEASUREMENT_HISTORY_LIMIT", "10000")))
POLL_SECONDS = max(1.0, float(os.environ.get("POWERGATEWAY_MEASUREMENT_POLL_SECONDS", "2")))
_lock = threading.Lock()
_last_identity = ""


def _read_latest() -> dict[str, Any]:
    try:
        value = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _identity(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("telegram_sha256") or snapshot.get("received_at") or json.dumps(snapshot, sort_keys=True))


def _normalised_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat()
    measurements = snapshot.get("measurements")
    if not isinstance(measurements, list):
        measurements = []
        ignored = {"gateway", "source", "received_at", "telegram_sha256", "simulation", "simulation_profile", "raw"}
        for key, value in snapshot.items():
            if key not in ignored and isinstance(value, (int, float)):
                measurements.append({"key": key, "name": key, "value": value, "unit": "", "obis": ""})
    return {
        "captured_at": captured_at,
        "received_at": snapshot.get("received_at") or captured_at,
        "gateway": snapshot.get("gateway", ""),
        "source": snapshot.get("source", ""),
        "telegram_sha256": snapshot.get("telegram_sha256", ""),
        "measurements": measurements,
    }


def _trim_history() -> None:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_SNAPSHOTS:
        return
    temporary = HISTORY_PATH.with_suffix(".jsonl.tmp")
    temporary.write_text("\n".join(lines[-MAX_SNAPSHOTS:]) + "\n", encoding="utf-8")
    temporary.replace(HISTORY_PATH)


def _append_snapshot(snapshot: dict[str, Any]) -> None:
    global _last_identity
    identity = _identity(snapshot)
    if not identity or identity == _last_identity:
        return
    record = _normalised_snapshot(snapshot)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with HISTORY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        _last_identity = identity
        _trim_history()


def _collector() -> None:
    while True:
        snapshot = _read_latest()
        if snapshot:
            try:
                _append_snapshot(snapshot)
            except OSError:
                pass
        time.sleep(POLL_SECONDS)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _records(hours: float) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(0.0, min(hours, 168.0)))
    rows: list[dict[str, Any]] = []
    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                timestamp = _parse_time(record.get("received_at") or record.get("captured_at"))
                if timestamp and timestamp >= cutoff:
                    rows.append(record)
    except OSError:
        pass
    return rows


@app.get("/_internal/measurements/keys")
@legacy.login_required
def measurement_keys() -> Response:
    keys: dict[str, dict[str, str]] = {}
    records = _records(168)
    for record in records:
        for item in record.get("measurements", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("obis") or "").strip()
            if key:
                keys[key] = {
                    "key": key,
                    "name": str(item.get("name") or key),
                    "unit": str(item.get("unit") or ""),
                    "obis": str(item.get("obis") or ""),
                }
    return jsonify({"items": sorted(keys.values(), key=lambda item: item["name"]), "snapshots": len(records)})


@app.get("/_internal/measurements/export.csv")
@legacy.login_required
def measurement_export_csv() -> Response:
    try:
        hours = float(request.args.get("hours", "24"))
    except ValueError:
        hours = 24.0
    selected_key = str(request.args.get("key", "")).strip()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Empfangen am", "Aufgezeichnet am", "Datenquelle", "Messwert", "Bezeichnung", "Rohwert", "Einheit", "OBIS", "Telegramm-SHA256"])
    count = 0
    for record in _records(hours):
        for item in record.get("measurements", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("obis") or "")
            if selected_key and key != selected_key:
                continue
            writer.writerow([
                record.get("received_at", ""), record.get("captured_at", ""), record.get("source", ""),
                key, item.get("name", ""), item.get("value", ""), item.get("unit", ""),
                item.get("obis", ""), record.get("telegram_sha256", ""),
            ])
            count += 1
    filename_key = selected_key.replace("/", "-").replace(" ", "_") if selected_key else "alle"
    response = Response("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="powergateway-messwerte-{filename_key}-{int(hours)}h.csv"'
    response.headers["X-PowerGateway-Rows"] = str(count)
    return response


threading.Thread(target=_collector, name="measurement-export-collector", daemon=True).start()

SECTION = r'''<div class="section card"><div class="toolbar"><div><h2>Rohmesswerte herunterladen</h2><div class="muted">Diagnosedaten zum Prüfen von Einheiten, Zeitstempeln und Diagrammwerten.</div></div><button class="secondary" onclick="loadMeasurementExport()">Messwerte laden</button></div><div class="form-grid"><div class="field"><label>Messwert</label><select id="exportMeasurementKey"><option value="">Alle Messwerte</option></select></div><div class="field"><label>Zeitraum</label><select id="exportMeasurementHours"><option value="1">Letzte Stunde</option><option value="6">Letzte 6 Stunden</option><option value="24" selected>Letzte 24 Stunden</option><option value="72">Letzte 3 Tage</option><option value="168">Letzte 7 Tage</option></select></div><div class="field full"><a id="measurementCsvLink" class="button" href="/_internal/measurements/export.csv?hours=24">CSV herunterladen</a> <span id="measurementExportInfo" class="muted"></span></div></div></div>'''
JS = r'''async function loadMeasurementExport(){try{const d=await api('/_internal/measurements/keys');const s=$('exportMeasurementKey'),current=s.value;s.innerHTML='<option value="">Alle Messwerte</option>'+(d.items||[]).map(x=>`<option value="${esc(x.key)}">${esc(x.name)}${x.unit?' ('+esc(x.unit)+')':''}${x.obis?' · '+esc(x.obis):''}</option>`).join('');s.value=current;$('measurementExportInfo').textContent=`${d.snapshots||0} Diagnose-Snapshots verfügbar`;updateMeasurementExportLink()}catch(e){notice(e.message,false)}}
function updateMeasurementExportLink(){const h=$('exportMeasurementHours').value||24,k=$('exportMeasurementKey').value||'';$('measurementCsvLink').href=`/_internal/measurements/export.csv?hours=${encodeURIComponent(h)}&key=${encodeURIComponent(k)}`}
'''
page = runtime.PAGE
page = page.replace('</section>\n<section id="meter"', SECTION + '</section>\n<section id="meter"')
page = page.replace('refresh();setInterval(refresh,5000);', JS + "$('exportMeasurementKey')?.addEventListener('change',updateMeasurementExportLink);$('exportMeasurementHours')?.addEventListener('change',updateMeasurementExportLink);loadMeasurementExport();refresh();setInterval(refresh,5000);")
runtime.PAGE = page
legacy.PAGE = page
