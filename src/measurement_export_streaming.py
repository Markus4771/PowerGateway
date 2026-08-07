#!/usr/bin/env python3
"""Robuster, speicherschonender CSV-Export fuer Messwertdiagnosen."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from flask import Response, request, stream_with_context

import measurement_export as previous

app = previous.app
legacy = previous.legacy
HISTORY_PATH = previous.HISTORY_PATH


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _csv_line(values: list[Any]) -> str:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, delimiter=";").writerow(values)
    return buffer.getvalue()


def _iter_export(hours: float, selected_key: str) -> Iterator[str]:
    yield "\ufeff" + _csv_line([
        "Empfangen am", "Aufgezeichnet am", "Datenquelle", "Messwert",
        "Bezeichnung", "Rohwert", "Einheit", "OBIS", "Telegramm-SHA256",
    ])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(0.0, min(hours, 168.0)))
    try:
        with HISTORY_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                timestamp = _parse_time(record.get("received_at") or record.get("captured_at"))
                if timestamp is None or timestamp < cutoff:
                    continue
                for item in record.get("measurements", []):
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or item.get("obis") or "")
                    if selected_key and key != selected_key:
                        continue
                    yield _csv_line([
                        record.get("received_at", ""),
                        record.get("captured_at", ""),
                        record.get("source", ""),
                        key,
                        item.get("name", ""),
                        item.get("value", ""),
                        item.get("unit", ""),
                        item.get("obis", ""),
                        record.get("telegram_sha256", ""),
                    ])
    except OSError:
        return


@app.get("/_internal/measurements/export-stream.csv")
@legacy.login_required
def measurement_export_stream_csv() -> Response:
    try:
        hours = float(request.args.get("hours", "24"))
    except ValueError:
        hours = 24.0
    hours = max(0.1, min(hours, 168.0))
    selected_key = str(request.args.get("key", "")).strip()
    filename_key = selected_key.replace("/", "-").replace(" ", "_") if selected_key else "alle"
    response = Response(
        stream_with_context(_iter_export(hours, selected_key)),
        content_type="text/csv; charset=utf-8",
        direct_passthrough=True,
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="powergateway-messwerte-{filename_key}-{int(hours)}h.csv"'
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Accel-Buffering"] = "no"
    return response


SCRIPT = r'''
(function(){
  function updateStreamingLink(){
    const h=document.getElementById('exportMeasurementHours');
    const k=document.getElementById('exportMeasurementKey');
    const a=document.getElementById('measurementCsvLink');
    if(!h||!k||!a)return;
    a.href='/_internal/measurements/export-stream.csv?hours='+encodeURIComponent(h.value||24)+'&key='+encodeURIComponent(k.value||'');
  }
  document.addEventListener('DOMContentLoaded',function(){
    const h=document.getElementById('exportMeasurementHours');
    const k=document.getElementById('exportMeasurementKey');
    if(h)h.addEventListener('change',updateStreamingLink);
    if(k)k.addEventListener('change',updateStreamingLink);
    updateStreamingLink();
  });
})();
'''

page = previous.runtime.PAGE
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
previous.runtime.PAGE = page
previous.legacy.PAGE = page
