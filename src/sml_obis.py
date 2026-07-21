"""Best-effort SML OBIS decoder for PowerGateway.

The decoder intentionally keeps transport handling separate from value decoding.
It scans SML list entries for the common sequence
OBIS, status, time, unit, scaler, value and returns normalized measurements.
Unknown values remain available with their raw OBIS identifier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


UNIT_NAMES = {
    27: "W",
    30: "Wh",
    32: "V",
    33: "A",
    35: "Hz",
}

KNOWN_OBIS = {
    "1-0:1.8.0*255": ("energy_import", "Energie Bezug", "kWh", "total_increasing"),
    "1-0:2.8.0*255": ("energy_export", "Energie Einspeisung", "kWh", "total_increasing"),
    "1-0:16.7.0*255": ("power_total", "Aktuelle Leistung", "W", "measurement"),
    "1-0:36.7.0*255": ("power_l1", "Leistung L1", "W", "measurement"),
    "1-0:56.7.0*255": ("power_l2", "Leistung L2", "W", "measurement"),
    "1-0:76.7.0*255": ("power_l3", "Leistung L3", "W", "measurement"),
    "1-0:32.7.0*255": ("voltage_l1", "Spannung L1", "V", "measurement"),
    "1-0:52.7.0*255": ("voltage_l2", "Spannung L2", "V", "measurement"),
    "1-0:72.7.0*255": ("voltage_l3", "Spannung L3", "V", "measurement"),
    "1-0:31.7.0*255": ("current_l1", "Strom L1", "A", "measurement"),
    "1-0:51.7.0*255": ("current_l2", "Strom L2", "A", "measurement"),
    "1-0:71.7.0*255": ("current_l3", "Strom L3", "A", "measurement"),
    "1-0:14.7.0*255": ("frequency", "Netzfrequenz", "Hz", "measurement"),
}


@dataclass(frozen=True)
class Measurement:
    key: str
    name: str
    obis: str
    value: float | int
    unit: str | None
    device_class: str | None = None
    state_class: str | None = None
    scaler: int = 0
    raw_value: int | float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def obis_to_string(value: bytes) -> str:
    if len(value) != 6:
        return value.hex()
    a, b, c, d, e, f = value
    return f"{a}-{b}:{c}.{d}.{e}*{f}"


def _read_tl(data: bytes, offset: int) -> tuple[int, int, int]:
    """Return type, payload length and new offset for a simple SML TL field."""
    if offset >= len(data):
        raise ValueError("TL außerhalb des Telegramms")
    first = data[offset]
    offset += 1
    field_type = (first >> 4) & 0x07
    length = first & 0x0F
    if first & 0x80:
        # Multi-byte lengths are uncommon for scalar list entries. Support them
        # without interpreting type bits from continuation bytes.
        while True:
            if offset >= len(data):
                raise ValueError("Unvollständige TL-Länge")
            byte = data[offset]
            offset += 1
            length = (length << 4) | (byte & 0x0F)
            if not byte & 0x80:
                break
    header_length = offset
    payload_length = max(0, length - (header_length - (offset - 1)))
    # For ordinary one-byte TL fields, length includes the TL byte.
    if first & 0x80 == 0:
        payload_length = max(0, length - 1)
    return field_type, payload_length, offset


def _decode_scalar(data: bytes, offset: int) -> tuple[Any, int]:
    field_type, length, payload_offset = _read_tl(data, offset)
    end = payload_offset + length
    if end > len(data):
        raise ValueError("Unvollständiger SML-Wert")
    payload = data[payload_offset:end]
    if field_type == 0:
        return payload, end
    if field_type == 5:
        return int.from_bytes(payload, "big", signed=True), end
    if field_type == 6:
        return int.from_bytes(payload, "big", signed=False), end
    if field_type == 4:
        return bool(payload[-1]) if payload else False, end
    return payload, end


def _normalize(obis: str, raw_value: int | float, scaler: int, unit_code: int | None) -> Measurement:
    value: float | int = raw_value * (10 ** scaler)
    unit = UNIT_NAMES.get(unit_code) if unit_code is not None else None
    key = "obis_" + obis.replace("-", "_").replace(":", "_").replace(".", "_").replace("*", "_")
    name = obis
    state_class = None
    device_class = None
    if obis in KNOWN_OBIS:
        key, name, preferred_unit, state_class = KNOWN_OBIS[obis]
        if preferred_unit == "kWh" and unit == "Wh":
            value = value / 1000
            unit = "kWh"
        else:
            unit = preferred_unit or unit
        if unit in {"Wh", "kWh"}:
            device_class = "energy"
        elif unit == "W":
            device_class = "power"
        elif unit == "V":
            device_class = "voltage"
        elif unit == "A":
            device_class = "current"
        elif unit == "Hz":
            device_class = "frequency"
    return Measurement(key, name, obis, value, unit, device_class, state_class, scaler, raw_value)


def decode_obis_values(frame: bytes) -> list[Measurement]:
    """Extract common OBIS list entries from an SML frame.

    This is deliberately tolerant: malformed candidates are skipped so one
    manufacturer-specific field cannot discard the complete telegram.
    """
    results: list[Measurement] = []
    seen: set[tuple[str, float | int]] = set()
    for index in range(0, max(0, len(frame) - 7)):
        # OBIS octet strings are encoded as TL 0x07 followed by six bytes.
        if frame[index] != 0x07:
            continue
        obis_bytes = frame[index + 1:index + 7]
        if len(obis_bytes) != 6 or obis_bytes[0] > 1:
            continue
        try:
            cursor = index + 7
            # List entry fields after OBIS: status, value time, unit, scaler, value.
            _, cursor = _decode_scalar(frame, cursor)
            _, cursor = _decode_scalar(frame, cursor)
            unit_value, cursor = _decode_scalar(frame, cursor)
            scaler_value, cursor = _decode_scalar(frame, cursor)
            raw_value, _ = _decode_scalar(frame, cursor)
            if not isinstance(raw_value, (int, float)):
                continue
            scaler = int(scaler_value) if isinstance(scaler_value, int) else 0
            unit_code = int(unit_value) if isinstance(unit_value, int) else None
            obis = obis_to_string(obis_bytes)
            measurement = _normalize(obis, raw_value, scaler, unit_code)
            identity = (measurement.obis, measurement.value)
            if identity not in seen:
                results.append(measurement)
                seen.add(identity)
        except (ValueError, IndexError, OverflowError):
            continue
    return results
