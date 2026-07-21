"""SML/OBIS decoding and registry for PowerGateway.

The module intentionally keeps serial transport handling separate from value
interpretation. It scans SML list entries, normalizes common German meter
values and preserves unknown numeric OBIS values for diagnostics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


UNIT_NAMES = {
    9: "°",
    22: "varh",
    23: "VAh",
    27: "W",
    28: "VA",
    29: "var",
    30: "Wh",
    31: "A",
    32: "V",
    33: "V/m",
    35: "Hz",
    44: "s",
    45: "min",
    46: "h",
    55: "%",
}


@dataclass(frozen=True)
class ObisDefinition:
    key: str
    name: str
    unit: str | None = None
    state_class: str | None = None
    device_class: str | None = None
    diagnostic: bool = False


OBIS_REGISTRY: dict[str, ObisDefinition] = {
    # Wirkenergie Bezug
    "1-0:1.8.0*255": ObisDefinition("energy_import", "Energie Bezug gesamt", "kWh", "total_increasing", "energy"),
    "1-0:1.8.1*255": ObisDefinition("energy_import_tariff_1", "Energie Bezug Tarif 1", "kWh", "total_increasing", "energy"),
    "1-0:1.8.2*255": ObisDefinition("energy_import_tariff_2", "Energie Bezug Tarif 2", "kWh", "total_increasing", "energy"),
    # Wirkenergie Einspeisung
    "1-0:2.8.0*255": ObisDefinition("energy_export", "Energie Einspeisung gesamt", "kWh", "total_increasing", "energy"),
    "1-0:2.8.1*255": ObisDefinition("energy_export_tariff_1", "Energie Einspeisung Tarif 1", "kWh", "total_increasing", "energy"),
    "1-0:2.8.2*255": ObisDefinition("energy_export_tariff_2", "Energie Einspeisung Tarif 2", "kWh", "total_increasing", "energy"),
    # Leistung gesamt und je Phase. Manche Zähler nutzen 21/41/61, andere 36/56/76.
    "1-0:16.7.0*255": ObisDefinition("power_total", "Aktuelle Leistung", "W", "measurement", "power"),
    "1-0:21.7.0*255": ObisDefinition("power_l1", "Leistung L1", "W", "measurement", "power"),
    "1-0:41.7.0*255": ObisDefinition("power_l2", "Leistung L2", "W", "measurement", "power"),
    "1-0:61.7.0*255": ObisDefinition("power_l3", "Leistung L3", "W", "measurement", "power"),
    "1-0:36.7.0*255": ObisDefinition("power_l1", "Leistung L1", "W", "measurement", "power"),
    "1-0:56.7.0*255": ObisDefinition("power_l2", "Leistung L2", "W", "measurement", "power"),
    "1-0:76.7.0*255": ObisDefinition("power_l3", "Leistung L3", "W", "measurement", "power"),
    # Spannung und Strom
    "1-0:32.7.0*255": ObisDefinition("voltage_l1", "Spannung L1", "V", "measurement", "voltage"),
    "1-0:52.7.0*255": ObisDefinition("voltage_l2", "Spannung L2", "V", "measurement", "voltage"),
    "1-0:72.7.0*255": ObisDefinition("voltage_l3", "Spannung L3", "V", "measurement", "voltage"),
    "1-0:31.7.0*255": ObisDefinition("current_l1", "Strom L1", "A", "measurement", "current"),
    "1-0:51.7.0*255": ObisDefinition("current_l2", "Strom L2", "A", "measurement", "current"),
    "1-0:71.7.0*255": ObisDefinition("current_l3", "Strom L3", "A", "measurement", "current"),
    # Netzqualität
    "1-0:14.7.0*255": ObisDefinition("frequency", "Netzfrequenz", "Hz", "measurement", "frequency"),
    "1-0:13.7.0*255": ObisDefinition("power_factor", "Leistungsfaktor", None, "measurement", "power_factor"),
    "1-0:33.7.0*255": ObisDefinition("power_factor_l1", "Leistungsfaktor L1", None, "measurement", "power_factor"),
    "1-0:53.7.0*255": ObisDefinition("power_factor_l2", "Leistungsfaktor L2", None, "measurement", "power_factor"),
    "1-0:73.7.0*255": ObisDefinition("power_factor_l3", "Leistungsfaktor L3", None, "measurement", "power_factor"),
    # Blindleistung
    "1-0:3.8.0*255": ObisDefinition("reactive_energy_import", "Blindenergie Bezug", "kvarh", "total_increasing"),
    "1-0:4.8.0*255": ObisDefinition("reactive_energy_export", "Blindenergie Abgabe", "kvarh", "total_increasing"),
    "1-0:3.7.0*255": ObisDefinition("reactive_power_import", "Blindleistung Bezug", "var", "measurement"),
    "1-0:4.7.0*255": ObisDefinition("reactive_power_export", "Blindleistung Abgabe", "var", "measurement"),
}

# Backwards-compatible tuple view used by the MQTT discovery wrapper.
KNOWN_OBIS = {
    obis: (definition.key, definition.name, definition.unit, definition.state_class)
    for obis, definition in OBIS_REGISTRY.items()
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
    quality: str = "good"
    known: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def obis_to_string(value: bytes) -> str:
    if len(value) != 6:
        return value.hex()
    a, b, c, d, e, f = value
    return f"{a}-{b}:{c}.{d}.{e}*{f}"


def _read_tl(data: bytes, offset: int) -> tuple[int, int, int]:
    """Return type, payload length and payload offset for an SML TL field."""
    if offset >= len(data):
        raise ValueError("TL außerhalb des Telegramms")
    first = data[offset]
    offset += 1
    field_type = (first >> 4) & 0x07
    length = first & 0x0F
    header_bytes = 1
    if first & 0x80:
        while True:
            if offset >= len(data):
                raise ValueError("Unvollständige TL-Länge")
            byte = data[offset]
            offset += 1
            header_bytes += 1
            length = (length << 4) | (byte & 0x0F)
            if not byte & 0x80:
                break
    return field_type, max(0, length - header_bytes), offset


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


def _generic_key(obis: str) -> str:
    return "obis_" + obis.replace("-", "_").replace(":", "_").replace(".", "_").replace("*", "_")


def _normalize(obis: str, raw_value: int | float, scaler: int, unit_code: int | None) -> Measurement:
    value: float | int = raw_value * (10 ** scaler)
    reported_unit = UNIT_NAMES.get(unit_code) if unit_code is not None else None
    definition = OBIS_REGISTRY.get(obis)

    if definition is None:
        return Measurement(
            key=_generic_key(obis),
            name=obis,
            obis=obis,
            value=value,
            unit=reported_unit,
            scaler=scaler,
            raw_value=raw_value,
            known=False,
        )

    unit = definition.unit or reported_unit
    if definition.unit == "kWh" and reported_unit == "Wh":
        value /= 1000
    elif definition.unit == "kvarh" and reported_unit == "varh":
        value /= 1000

    return Measurement(
        key=definition.key,
        name=definition.name,
        obis=obis,
        value=value,
        unit=unit,
        device_class=definition.device_class,
        state_class=definition.state_class,
        scaler=scaler,
        raw_value=raw_value,
    )


def decode_obis_values(frame: bytes) -> list[Measurement]:
    """Extract numeric OBIS list entries from an SML frame.

    Malformed candidates are skipped so manufacturer-specific fields do not
    discard an otherwise valid telegram. Duplicate aliases are collapsed by
    normalized key; the first occurrence in the telegram wins.
    """
    results: list[Measurement] = []
    seen_keys: set[str] = set()
    for index in range(0, max(0, len(frame) - 7)):
        if frame[index] != 0x07:
            continue
        obis_bytes = frame[index + 1:index + 7]
        if len(obis_bytes) != 6 or obis_bytes[0] > 1:
            continue
        try:
            cursor = index + 7
            _, cursor = _decode_scalar(frame, cursor)  # status
            _, cursor = _decode_scalar(frame, cursor)  # value time
            unit_value, cursor = _decode_scalar(frame, cursor)
            scaler_value, cursor = _decode_scalar(frame, cursor)
            raw_value, _ = _decode_scalar(frame, cursor)
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                continue
            scaler = int(scaler_value) if isinstance(scaler_value, int) else 0
            unit_code = int(unit_value) if isinstance(unit_value, int) else None
            measurement = _normalize(obis_to_string(obis_bytes), raw_value, scaler, unit_code)
            if measurement.key not in seen_keys:
                results.append(measurement)
                seen_keys.add(measurement.key)
        except (ValueError, IndexError, OverflowError):
            continue
    return results
