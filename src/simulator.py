"""Hardwareunabhängiger SML-Simulator für PowerGateway.

Die Simulation erzeugt echte, vom vorhandenen Parser lesbare SML-Transportframes.
Damit laufen OBIS-Dekodierung, MQTT, Pufferung und WebGUI über denselben Pfad wie
bei einem angeschlossenen USB-IR-Lesekopf.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any

SML_START = bytes.fromhex("1b1b1b1b01010101")
SML_END = bytes.fromhex("1b1b1b1b1a")


@dataclass(frozen=True)
class SimulatorProfile:
    name: str
    base_power: int
    export: bool = False
    three_phase: bool = True
    unknown_obis: bool = False


PROFILES: dict[str, SimulatorProfile] = {
    "generic": SimulatorProfile("Generischer Haushaltszähler", 650),
    "emh": SimulatorProfile("EMH eHZ", 820),
    "easymeter": SimulatorProfile("EasyMeter Q3", 430),
    "iskra": SimulatorProfile("Iskra MT681", 1050),
    "kaifa": SimulatorProfile("Kaifa MA309", 720),
    "solar": SimulatorProfile("Zweirichtungszähler mit PV", 1800, export=True),
    "unknown": SimulatorProfile("Zähler mit unbekannter OBIS-Kennzahl", 500, unknown_obis=True),
}


def _signed(value: int, length: int = 4) -> bytes:
    return int(value).to_bytes(length, "big", signed=True)


def _unsigned(value: int, length: int = 4) -> bytes:
    return max(0, int(value)).to_bytes(length, "big", signed=False)


def sml_entry(obis: tuple[int, int, int, int, int, int], unit: int, scaler: int, value: int, *, signed: bool = False) -> bytes:
    payload = _signed(value) if signed else _unsigned(value)
    value_type = b"\x55" if signed else b"\x65"
    return (
        b"\x77"
        + b"\x07" + bytes(obis)
        + b"\x01"  # Status optional
        + b"\x01"  # Zeit optional
        + b"\x62" + bytes([unit])
        + b"\x52" + int(scaler).to_bytes(1, "big", signed=True)
        + value_type + payload
        + b"\x01"
    )


class SmlSimulator:
    def __init__(self, profile: str = "generic", interval: float = 5.0, seed: int | None = None) -> None:
        if profile not in PROFILES:
            raise ValueError(f"Unbekanntes Simulatorprofil: {profile}")
        self.profile = PROFILES[profile]
        self.profile_key = profile
        self.interval = max(0.1, float(interval))
        self.random = random.Random(seed)
        self.started = time.monotonic()
        self.energy_import_wh = 12_345_000
        self.energy_export_wh = 1_250_000 if self.profile.export else 0

    def measurements(self) -> list[dict[str, Any]]:
        elapsed = time.monotonic() - self.started
        wave = math.sin(elapsed / 18.0)
        jitter = self.random.randint(-80, 80)
        power = max(0, self.profile.base_power + int(350 * wave) + jitter)
        exporting = self.profile.export and wave < -0.35
        signed_power = -power if exporting else power
        seconds = self.interval
        if exporting:
            self.energy_export_wh += int(power * seconds / 3600)
        else:
            self.energy_import_wh += int(power * seconds / 3600)

        phase_power = [signed_power // 3, signed_power // 3, signed_power - 2 * (signed_power // 3)]
        values: list[dict[str, Any]] = [
            {"obis": (1, 0, 1, 8, 0, 255), "unit": 30, "scaler": 0, "value": self.energy_import_wh},
            {"obis": (1, 0, 2, 8, 0, 255), "unit": 30, "scaler": 0, "value": self.energy_export_wh},
            {"obis": (1, 0, 16, 7, 0, 255), "unit": 27, "scaler": 0, "value": signed_power, "signed": True},
            {"obis": (1, 0, 14, 7, 0, 255), "unit": 35, "scaler": -2, "value": 5000},
        ]
        if self.profile.three_phase:
            for phase, prefix in enumerate((21, 41, 61)):
                voltage = 2300 + self.random.randint(-25, 25)
                current = max(0, abs(phase_power[phase]) * 10 // max(1, voltage))
                values.extend([
                    {"obis": (1, 0, prefix, 7, 0, 255), "unit": 27, "scaler": 0, "value": phase_power[phase], "signed": True},
                    {"obis": (1, 0, 32 + phase * 20, 7, 0, 255), "unit": 32, "scaler": -1, "value": voltage},
                    {"obis": (1, 0, 31 + phase * 20, 7, 0, 255), "unit": 33, "scaler": -2, "value": current},
                ])
        if self.profile.unknown_obis:
            values.append({"obis": (1, 0, 96, 50, 1, 255), "unit": 27, "scaler": 0, "value": 7})
        return values

    def frame(self) -> bytes:
        body = b"".join(sml_entry(**item) for item in self.measurements())
        # Der aktuelle Transportleser erwartet nach der Endmarke Füllbyte und CRC.
        # Die CRC-Validierung folgt in einer späteren Stufe; die Bytes sind bewusst stabil.
        return SML_START + body + SML_END + b"\x00\x00\x00"


class SimulatedSerial:
    """Minimaler pyserial-kompatibler Datenstrom für den bestehenden Hauptdienst."""

    def __init__(self, simulator: SmlSimulator) -> None:
        self.simulator = simulator
        self.is_open = True
        self._buffer = bytearray()
        self._next_frame = 0.0

    def read(self, size: int = 1024) -> bytes:
        if not self.is_open:
            return b""
        now = time.monotonic()
        if not self._buffer and now >= self._next_frame:
            self._buffer.extend(self.simulator.frame())
            self._next_frame = now + self.simulator.interval
        if not self._buffer:
            time.sleep(min(0.1, max(0.0, self._next_frame - now)))
            return b""
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def close(self) -> None:
        self.is_open = False
