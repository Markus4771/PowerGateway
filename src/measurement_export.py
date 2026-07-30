#!/usr/bin/env python3
"""Begrenzter Diagnoseverlauf, Telegrammstatistik und CSV-Export."""
from __future__ import annotations

import csv
import io
import json
import os
import statistics
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


def _telegram_stats(hours: float = 1.0) -> dict[str, Any]:
    records = _records(hours)
    timestamps = sorted(
        timestamp for record in records
        if (timestamp := _parse_time(record.get("received_at") or record.get("captured_at"))) is not None
    )
    now = datetime.now(timezone.utc)
    if not timestamps:
        return {
            "telegrams": 0, "telegrams_per_minute": 0.0, "average_interval_seconds": None,
            "median_interval_seconds": None, "last_telegram_at": None, "seconds_since_last": None,
            "largest_gap_seconds": None, "gap_count": 0, "estimated_missing": 0, "status": "no_data",
            "window_hours": hours,
        }
    intervals = [(right - left).total_seconds() for left, right in zip(timestamps, timestamps[1:]) if right > left]
    average = statistics.fmean(intervals) if intervals else None
    median = statistics.median(intervals) if intervals else None
    baseline = median or average
    gap_threshold = max((baseline or POLL_SECONDS) * 2.5, POLL_SECONDS * 2.5)
    gaps = [value for value in intervals if value > gap_threshold]
    estimated_missing = 0
    if baseline and baseline > 0:
        estimated_missing = sum(max(0, round(value / baseline) - 1) for value in gaps)
    observed_seconds = max(1.0, (timestamps[-1] - timestamps[0]).total_seconds()) if len(timestamps) > 1 else max(1.0, hours * 3600)
    rate = len(timestamps) * 60.0 / observed_seconds
    seconds_since_last = max(0.0, (now - timestamps[-1]).total_seconds())
    stale_limit = max((baseline or POLL_SECONDS) * 3.0, 10.0)
    status = "stale" if seconds_since_last > stale_limit else ("gaps" if gaps else "ok")
    return {
        "telegrams": len(timestamps),
        "telegrams_per_minute": round(rate, 2),
        "average_interval_seconds": round(average, 3) if average is not None else None,
        "median_interval_seconds": round(median, 3) if median is not None else None,
        "last_telegram_at": timestamps[-1].isoformat(),
        "seconds_since_last": round(seconds_since_last, 1),
        "largest_gap_seconds": round(max(intervals), 3) if intervals else None,
        "gap_count": len(gaps),
        "estimated_missing": estimated_missing,
        "gap_threshold_seconds": round(gap_threshold, 3),
        "status": status,
        "window_hours": hours,
        "collector_poll_seconds": POLL_SECONDS,
    }


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
                    "key": key, "name": str(item.get("name") or key),
                    "unit": str(item.get("unit") or ""), "obis": str(item.get("obis") or ""),
                }
    return jsonify({"items": sorted(keys.values(), key=lambda item: item["name"]), "snapshots": len(records)})


@app.get("/_internal/measurements/telegram-stats")
@legacy.login_required
def measurement_telegram_stats() -> Response:
    try:
        hours = float(request.args.get("hours", "1"))
    except ValueError:
        hours = 1.0
    return jsonify(_telegram_stats(max(0.1, min(hours, 24.0))))


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

SECTION = r'''<div class="section card"><div class="toolbar"><div><h2>Telegramm- und Messwertdiagnose</h2><div class="muted">Tatsächliche Empfangsrate des Zählers, erkennbare Aussetzer und Rohdatenexport.</div></div><button class="secondary" onclick="loadMeasurementDiagnostics()">Neu prüfen</button></div><div id="telegramStats" class="grid"><div class="card"><div class="muted">Telegramme</div><div class="value">–</div></div><div class="card"><div class="muted">Pro Minute</div><div class="value">–</div></div><div class="card"><div class="muted">Ø Intervall</div><div class="value">–</div></div><div class="card"><div class="muted">Seit letztem Telegramm</div><div class="value">–</div></div><div class="card"><div class="muted">Erkannte Aussetzer</div><div class="value">–</div></div><div class="card"><div class="muted">Größte Lücke</div><div class="value">–</div></div></div><div id="telegramStatusInfo" class="section muted"></div><div class="form-grid"><div class="field"><label>Messwert</label><select id="exportMeasurementKey"><option value="">Alle Messwerte</option></select></div><div class="field"><label>Zeitraum</label><select id="exportMeasurementHours"><option value="1">Letzte Stunde</option><option value="6">Letzte 6 Stunden</option><option value="24" selected>Letzte 24 Stunden</option><option value="72">Letzte 3 Tage</option><option value="168">Letzte 7 Tage</option></select></div><div class="field full"><a id="measurementCsvLink" class="button" href="/_internal/measurements/export.csv?hours=24">CSV herunterladen</a> <span id="measurementExportInfo" class="muted"></span></div></div></div>'''
JS = r'''function secondsText(v){if(v===null||v===undefined)return '–';const n=Number(v);return n<60?`${n.toFixed(n<10?1:0)} s`:`${(n/60).toFixed(1)} min`}
async function loadTelegramStats(){try{const d=await api('/_internal/measurements/telegram-stats?hours=1');const cards=$('telegramStats').querySelectorAll('.value');cards[0].textContent=d.telegrams??0;cards[1].textContent=Number(d.telegrams_per_minute||0).toFixed(2);cards[2].textContent=secondsText(d.average_interval_seconds);cards[3].textContent=secondsText(d.seconds_since_last);cards[4].textContent=`${d.gap_count||0}${d.estimated_missing?` (~${d.estimated_missing} fehlend)`:''}`;cards[5].textContent=secondsText(d.largest_gap_seconds);const labels={ok:'Empfang läuft regelmäßig.',gaps:'Es wurden auffällige Zeitlücken erkannt.',stale:'Seit längerer Zeit wurde kein neues Telegramm empfangen.',no_data:'Noch keine Telegrammdaten vorhanden.'};$('telegramStatusInfo').textContent=`${labels[d.status]||''} Auswertung: letzte Stunde · Median ${secondsText(d.median_interval_seconds)} · Diagnoseabfrage alle ${d.collector_poll_seconds||2} s.`}catch(e){$('telegramStatusInfo').textContent=e.message}}
async function loadMeasurementExport(){try{const d=await api('/_internal/measurements/keys');const s=$('exportMeasurementKey'),current=s.value;s.innerHTML='<option value="">Alle Messwerte</option>'+(d.items||[]).map(x=>`<option value="${esc(x.key)}">${esc(x.name)}${x.unit?' ('+esc(x.unit)+')':''}${x.obis?' · '+esc(x.obis):''}</option>`).join('');s.value=current;$('measurementExportInfo').textContent=`${d.snapshots||0} Diagnose-Snapshots verfügbar`;updateMeasurementExportLink()}catch(e){notice(e.message,false)}}
function updateMeasurementExportLink(){const h=$('exportMeasurementHours').value||24,k=$('exportMeasurementKey').value||'';$('measurementCsvLink').href=`/_internal/measurements/export.csv?hours=${encodeURIComponent(h)}&key=${encodeURIComponent(k)}`}
function loadMeasurementDiagnostics(){loadTelegramStats();loadMeasurementExport()}
'''
page = runtime.PAGE
page = page.replace('</section>\n<section id="meter"', SECTION + '</section>\n<section id="meter"')
page = page.replace('refresh();setInterval(refresh,5000);', JS + "$('exportMeasurementKey')?.addEventListener('change',updateMeasurementExportLink);$('exportMeasurementHours')?.addEventListener('change',updateMeasurementExportLink);loadMeasurementDiagnostics();setInterval(loadTelegramStats,10000);refresh();setInterval(refresh,5000);")
runtime.PAGE = page
legacy.PAGE = page
