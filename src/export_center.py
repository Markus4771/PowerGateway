#!/usr/bin/env python3
"""Integriertes Export-Center für PowerGateway.

Erzeugt CSV-, JSON-, XLSX-, PDF- und ZIP-Exporte aus der lokalen
Energiehistorie. Alle Dateien werden in /var/lib/powergateway/exports
archiviert und können über die Weboberfläche erneut geladen oder gelöscht
werden. Die Implementierung verwendet ausschließlich die Python-
Standardbibliothek.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from flask import Response, jsonify, request, send_file

import energy_history

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime

EXPORT_DIR = Path('/var/lib/powergateway/exports')
ALLOWED_FORMATS = {'csv', 'json', 'xlsx', 'pdf', 'zip'}
COLUMNS = (
    ('timestamp', 'Zeitstempel'),
    ('power_w', 'Leistung (W)'),
    ('energy_kwh', 'Zählerstand (kWh)'),
    ('voltage_v', 'Spannung (V)'),
    ('current_a', 'Strom (A)'),
    ('frequency_hz', 'Frequenz (Hz)'),
    ('power_factor', 'Leistungsfaktor'),
)


def _safe_name(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9_.-]+', '_', value).strip('._')
    return value[:120] or 'PowerGateway_Export'


def _range_rows(name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if name not in energy_history.RANGES:
        name = '7d'
    start, end, _bucket = energy_history._bounds(name)
    settings = energy_history._settings()
    reset_ts = max(0, int(settings.get('meter_reset_ts', 0) or 0))
    effective_start = max(start, reset_ts)
    with energy_history._connect() as db:
        rows = db.execute(
            '''SELECT ts, power_w, energy_kwh, voltage_v, current_a,
                      frequency_hz, power_factor
               FROM measurements
              WHERE ts BETWEEN ? AND ?
              ORDER BY ts ASC''',
            (effective_start, end),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['timestamp'] = datetime.fromtimestamp(int(item.pop('ts'))).astimezone().isoformat(timespec='seconds')
        result.append(item)
    summary = energy_history.history(name)
    summary['exported_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
    summary['measurement_count'] = len(result)
    return summary, result


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=';', lineterminator='\n')
    writer.writerow([label for _key, label in COLUMNS])
    for row in rows:
        writer.writerow([row.get(key, '') if row.get(key) is not None else '' for key, _label in COLUMNS])
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def _json_bytes(summary: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    document = {
        'product': 'PowerGateway',
        'version': '1.3.6-dev',
        'summary': summary,
        'measurements': rows,
    }
    return json.dumps(document, ensure_ascii=False, indent=2, default=str).encode('utf-8')


def _xlsx_cell(ref: str, value: Any, numeric: bool = False) -> str:
    if value is None or value == '':
        return f'<c r="{ref}"/>'
    if numeric:
        try:
            return f'<c r="{ref}"><v>{float(value)}</v></c>'
        except (TypeError, ValueError):
            pass
    text = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _col_name(index: int) -> str:
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(headers: list[str], rows: list[list[Any]], numeric_from: int = 1) -> str:
    xml_rows = []
    all_rows = [headers] + rows
    for row_index, values in enumerate(all_rows, 1):
        cells = []
        for col_index, value in enumerate(values, 1):
            ref = f'{_col_name(col_index)}{row_index}'
            cells.append(_xlsx_cell(ref, value, numeric=row_index > 1 and col_index > numeric_from))
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' \
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>' \
        '<sheetData>' + ''.join(xml_rows) + '</sheetData><autoFilter ref="A1:' + _col_name(len(headers)) + str(max(1, len(all_rows))) + '"/></worksheet>'


def _xlsx_bytes(summary: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    measurement_rows = [[row.get(key) for key, _label in COLUMNS] for row in rows]
    s = summary.get('summary', {})
    settings = summary.get('settings', {})
    summary_rows = [
        ['Zeitraum', summary.get('range')],
        ['Beginn', datetime.fromtimestamp(summary.get('start', 0)).astimezone().isoformat(timespec='seconds')],
        ['Ende', datetime.fromtimestamp(summary.get('end', 0)).astimezone().isoformat(timespec='seconds')],
        ['Messwerte', summary.get('measurement_count', 0)],
        ['Verbrauch (kWh)', s.get('consumption_kwh')],
        ['Kosten (EUR)', s.get('cost_eur')],
        ['Aktuelle Leistung (W)', s.get('current_power_w')],
        ['Tarifname', settings.get('tariff_name', '')],
        ['Arbeitspreis (EUR/kWh)', settings.get('price_eur_kwh')],
        ['Grundpreis (EUR/Monat)', settings.get('base_price_eur_month', 0)],
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Messwerte" sheetId="1" r:id="rId1"/><sheet name="Zusammenfassung" sheetId="2" r:id="rId2"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', _sheet_xml([label for _key, label in COLUMNS], measurement_rows))
        archive.writestr('xl/worksheets/sheet2.xml', _sheet_xml(['Kennzahl', 'Wert'], summary_rows, numeric_from=99))
    return buffer.getvalue()


def _pdf_escape(text: Any) -> str:
    return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)').encode('latin-1', 'replace').decode('latin-1')


def _pdf_bytes(summary: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    s = summary.get('summary', {})
    settings = summary.get('settings', {})
    lines = [
        'PowerGateway Energiebericht',
        '',
        f"Erstellt: {summary.get('exported_at', '')}",
        f"Zeitraum: {datetime.fromtimestamp(summary.get('start', 0)).astimezone():%d.%m.%Y %H:%M} - {datetime.fromtimestamp(summary.get('end', 0)).astimezone():%d.%m.%Y %H:%M}",
        f"Tarif: {settings.get('tariff_name', 'Standardtarif')}",
        '',
        f"Verbrauch: {s.get('consumption_kwh', 0)} kWh",
        f"Gesamtkosten: {s.get('cost_eur', 0)} EUR",
        f"Aktuelle Leistung: {s.get('current_power_w', 0)} W",
        f"Messwerte: {len(rows)}",
        '',
        'Die vollständigen Einzelmesswerte stehen im CSV-, JSON- oder Excel-Export zur Verfügung.',
    ]
    commands = ['BT', '/F1 18 Tf', '50 790 Td']
    for index, line in enumerate(lines):
        if index == 1:
            commands.append('/F1 11 Tf')
        commands.append(f'({_pdf_escape(line)}) Tj')
        commands.append('0 -24 Td')
    commands.append('ET')
    stream = '\n'.join(commands).encode('latin-1', 'replace')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = io.BytesIO(); out.write(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(out.tell()); out.write(f'{number} 0 obj\n'.encode()); out.write(obj); out.write(b'\nendobj\n')
    xref = out.tell(); out.write(f'xref\n0 {len(objects)+1}\n'.encode()); out.write(b'0000000000 65535 f \n')
    for offset in offsets[1:]: out.write(f'{offset:010d} 00000 n \n'.encode())
    out.write(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return out.getvalue()


def _build(fmt: str, range_name: str) -> tuple[str, bytes]:
    summary, rows = _range_rows(range_name)
    stamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S')
    base = _safe_name(f'PowerGateway_{range_name}_{stamp}')
    builders = {
        'csv': lambda: _csv_bytes(rows),
        'json': lambda: _json_bytes(summary, rows),
        'xlsx': lambda: _xlsx_bytes(summary, rows),
        'pdf': lambda: _pdf_bytes(summary, rows),
    }
    if fmt in builders:
        return f'{base}.{fmt}', builders[fmt]()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f'{base}.csv', _csv_bytes(rows))
        archive.writestr(f'{base}.json', _json_bytes(summary, rows))
        archive.writestr(f'{base}.xlsx', _xlsx_bytes(summary, rows))
        archive.writestr(f'{base}.pdf', _pdf_bytes(summary, rows))
        archive.writestr('info.txt', f'PowerGateway Export\nVersion: 1.3.6-dev\nZeitraum: {range_name}\nMesswerte: {len(rows)}\n')
    return f'{base}.zip', buffer.getvalue()


def _archive(filename: str, data: bytes) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / _safe_name(filename)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
    return path


@app.post('/_internal/export/create')
@legacy.login_required
def export_create() -> Response:
    data = request.get_json(silent=True) or {}
    fmt = str(data.get('format', 'zip')).lower()
    range_name = str(data.get('range', '7d'))
    if fmt not in ALLOWED_FORMATS:
        return jsonify({'ok': False, 'error': 'Nicht unterstütztes Exportformat.'}), 400
    try:
        filename, content = _build(fmt, range_name)
        path = _archive(filename, content)
        return jsonify({'ok': True, 'filename': path.name, 'size': path.stat().st_size, 'download_url': '/_internal/export/download/' + path.name})
    except Exception as exc:
        return jsonify({'ok': False, 'error': f'Export konnte nicht erzeugt werden: {exc}'}), 500


@app.get('/_internal/export/list')
@legacy.login_required
def export_list() -> Response:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(EXPORT_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file() and not path.name.endswith('.tmp'):
            stat = path.stat()
            files.append({'name': path.name, 'size': stat.st_size, 'created': int(stat.st_mtime), 'download_url': '/_internal/export/download/' + path.name})
    return jsonify({'ok': True, 'files': files, 'total_size': sum(item['size'] for item in files)})


def _resolved_export(name: str) -> Path | None:
    safe = _safe_name(name)
    path = EXPORT_DIR / safe
    try:
        if path.is_file() and path.resolve().parent == EXPORT_DIR.resolve():
            return path
    except OSError:
        return None
    return None


@app.get('/_internal/export/download/<name>')
@legacy.login_required
def export_download(name: str):
    path = _resolved_export(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Exportdatei nicht gefunden.'}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.delete('/_internal/export/<name>')
@legacy.login_required
def export_delete(name: str) -> Response:
    path = _resolved_export(name)
    if path is None:
        return jsonify({'ok': False, 'error': 'Exportdatei nicht gefunden.'}), 404
    path.unlink()
    return jsonify({'ok': True})


SECTION = r'''
<section id="exports" class="tab"><div class="toolbar"><div><h2>Export-Center</h2><div class="muted">Messwerte und Energieberichte erzeugen, herunterladen und verwalten.</div></div><button class="secondary" onclick="loadExports()">Archiv aktualisieren</button></div><div class="section export-form"><div class="form-grid"><label>Zeitraum<select id="exportRange"><option value="today">Heute</option><option value="yesterday">Gestern</option><option value="7d" selected>Letzte 7 Tage</option><option value="30d">Letzte 30 Tage</option><option value="month">Dieser Monat</option><option value="last_month">Letzter Monat</option><option value="year">Dieses Jahr</option></select></label><label>Format<select id="exportFormat"><option value="zip">ZIP-Komplettpaket</option><option value="pdf">PDF-Bericht</option><option value="xlsx">Excel (.xlsx)</option><option value="csv">CSV</option><option value="json">JSON</option></select></label></div><div class="export-actions"><button id="exportCreateButton" onclick="createExport()">Export erzeugen</button><span class="muted" id="exportProgress"></span></div></div><div class="section"><div class="toolbar"><div><h3>Export-Archiv</h3><div class="muted" id="exportArchiveInfo">Noch nicht geladen.</div></div></div><div class="table-wrap"><table><thead><tr><th>Datei</th><th>Erstellt</th><th>Größe</th><th>Aktionen</th></tr></thead><tbody id="exportRows"><tr><td colspan="4" class="muted">Noch keine Exporte geladen.</td></tr></tbody></table></div></div></section>
'''

STYLE = r'''
.export-form{max-width:850px}.export-actions{display:flex;gap:12px;align-items:center;margin-top:16px}.table-wrap{overflow-x:auto}.export-file{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9rem}.export-actions-cell{display:flex;gap:7px;flex-wrap:wrap}.export-actions-cell .danger{background:#fff0ee;color:var(--bad)}@media(max-width:600px){.export-actions{align-items:stretch;flex-direction:column}.export-actions button{width:100%}}
'''

JS = r'''
function exportSize(bytes){const u=['B','KB','MB','GB'];let n=Number(bytes)||0,i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return n.toLocaleString('de-DE',{maximumFractionDigits:1})+' '+u[i]}
async function loadExports(){try{const d=await api('/_internal/export/list');$('exportArchiveInfo').textContent=(d.files||[]).length+' Dateien · '+exportSize(d.total_size);$('exportRows').innerHTML=(d.files||[]).length?(d.files||[]).map(f=>`<tr><td class="export-file">${esc(f.name)}</td><td>${new Date(f.created*1000).toLocaleString('de-DE')}</td><td>${exportSize(f.size)}</td><td><div class="export-actions-cell"><a class="button secondary" href="${f.download_url}">Download</a><button class="danger" onclick="deleteExport('${encodeURIComponent(f.name)}')">Löschen</button></div></td></tr>`).join(''):'<tr><td colspan="4" class="muted">Noch keine Exporte vorhanden.</td></tr>'}catch(e){notice(e.message,false)}}
async function createExport(){const b=$('exportCreateButton');b.disabled=true;$('exportProgress').textContent='Export wird erstellt …';try{const d=await api('/_internal/export/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({range:$('exportRange').value,format:$('exportFormat').value})});notice('Export wurde erstellt.',true);$('exportProgress').innerHTML=`Fertig: <a href="${d.download_url}">${esc(d.filename)}</a> (${exportSize(d.size)})`;await loadExports()}catch(e){$('exportProgress').textContent='';notice(e.message,false)}finally{b.disabled=false}}
async function deleteExport(encoded){if(!confirm('Exportdatei wirklich löschen?'))return;try{await api('/_internal/export/'+encoded,{method:'DELETE'});notice('Export gelöscht.',true);await loadExports()}catch(e){notice(e.message,false)}}
'''

page = runtime.PAGE
page = page.replace('</style></head>', STYLE + '</style></head>')
page = page.replace('<button onclick="showTab(\'users\',this)">Benutzer</button>', '<button onclick="showTab(\'exports\',this)">Export-Center</button><button onclick="showTab(\'users\',this)">Benutzer</button>')
page = page.replace('<section id="users" class="tab">', SECTION + '<section id="users" class="tab">')
page = page.replace("if(id==='users')loadUsers();", "if(id==='exports')loadExports();if(id==='users')loadUsers();")
page = page.replace('refresh();setInterval(refresh,5000);', JS + 'refresh();setInterval(refresh,5000);')
runtime.PAGE = page
energy_history.legacy.PAGE = page
