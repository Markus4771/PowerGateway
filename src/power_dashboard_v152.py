#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from flask import Response, jsonify
import energy_history

app = energy_history.app
legacy = energy_history.legacy
runtime = energy_history.runtime
DATA_DIR = Path('/var/lib/powergateway')
LATEST_FILE = DATA_DIR / 'latest_values.json'
STATUS_FILE = DATA_DIR / 'status.json'

for key in ('power_total', '1-0:16.7.0*255'):
    if key not in energy_history.POWER_KEYS:
        energy_history.POWER_KEYS = (*energy_history.POWER_KEYS, key)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ('value', 'reading', 'wert'):
            if key in value:
                return _number(value[key])
        return None
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _find(data: Any) -> float | None:
    wanted = {'power_total', 'power_w', 'power', 'active_power', '1-0:16.7.0', '1-0:16.7.0*255'}
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in wanted:
                number = _number(value)
                if number is not None:
                    return number
        for nested in ('values', 'last_measurement', 'measurement', 'measurements'):
            found = _find(data.get(nested))
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                key = str(item.get('key') or item.get('obis') or '').lower()
                if key in wanted:
                    number = _number(item.get('value'))
                    if number is not None:
                        return number
    return None


@app.get('/_internal/power/live')
@legacy.login_required
def live_power() -> Response:
    latest = _read(LATEST_FILE)
    value = _find(latest)
    source = 'latest_values.json'
    received_at = latest.get('received_at') or latest.get('captured_at')
    if value is None:
        status = _read(STATUS_FILE)
        value = _find(status)
        source = 'status.json'
        received_at = status.get('measurement_received_at') or status.get('last_message_at') or status.get('updated_at')
    return jsonify({'ok': value is not None, 'power_w': value, 'source': source, 'received_at': received_at, 'obis': '1-0:16.7.0*255'})


CARD = r'''
<div class="section card" id="livePowerCard">
  <div class="toolbar">
    <div><h3>Momentane Leistung</h3><div class="muted">Direktwert aus dem SML-Telegramm · OBIS 1-0:16.7.0*255</div></div>
    <div class="value" id="livePowerValue">– W</div>
  </div>
  <div class="muted" id="livePowerTimestamp">Noch kein Messwert empfangen.</div>
</div>
'''
SCRIPT = r'''
async function loadLivePower(){
  const value=document.getElementById('livePowerValue');
  const stamp=document.getElementById('livePowerTimestamp');
  if(!value)return;
  try{
    const d=await api('/_internal/power/live');
    if(d.ok&&Number.isFinite(Number(d.power_w))){
      value.textContent=Number(d.power_w).toLocaleString('de-DE',{maximumFractionDigits:0})+' W';
      if(stamp)stamp.textContent=d.received_at?'Letzter Messwert: '+new Date(d.received_at).toLocaleString('de-DE'):'Livewert empfangen';
    }else{
      value.textContent='– W';
      if(stamp)stamp.textContent='Noch kein auswertbarer Leistungswert vorhanden.';
    }
  }catch(e){
    value.textContent='– W';
    if(stamp)stamp.textContent=e.message;
  }
}
document.addEventListener('DOMContentLoaded',function(){loadLivePower();setInterval(loadLivePower,5000)});
'''

page = runtime.PAGE
marker = '<div class="section energy-panel">'
if marker in page:
    page = page.replace(marker, CARD + marker, 1)
page = page.replace('</body>', '<script>' + SCRIPT + '</script></body>', 1)
runtime.PAGE = page
legacy.PAGE = page
