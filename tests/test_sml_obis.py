from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import sml_obis  # noqa: E402


def entry(obis: bytes, unit: int, scaler: int, value: int, *, signed: bool = False) -> bytes:
    value_bytes = int(value).to_bytes(4, "big", signed=signed)
    value_type = b"\x55" if signed else b"\x65"
    return (
        b"\x77"
        + b"\x07" + obis
        + b"\x01"
        + b"\x01"
        + b"\x62" + bytes([unit])
        + b"\x52" + int(scaler).to_bytes(1, "big", signed=True)
        + value_type + value_bytes
        + b"\x01"
    )


class ObisDecoderTests(unittest.TestCase):
    def test_import_energy_is_converted_to_kwh(self) -> None:
        frame = entry(bytes([1, 0, 1, 8, 0, 255]), 30, -1, 123456)
        values = sml_obis.decode_obis_values(frame)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].key, "energy_import")
        self.assertEqual(values[0].unit, "kWh")
        self.assertAlmostEqual(values[0].value, 12.3456)
        self.assertEqual(values[0].device_class, "energy")
        self.assertTrue(values[0].known)

    def test_tariff_energy(self) -> None:
        frame = entry(bytes([1, 0, 1, 8, 1, 255]), 30, 0, 25000)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.key, "energy_import_tariff_1")
        self.assertEqual(value.value, 25)

    def test_total_power(self) -> None:
        frame = entry(bytes([1, 0, 16, 7, 0, 255]), 27, 0, 824)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.key, "power_total")
        self.assertEqual(value.value, 824)
        self.assertEqual(value.unit, "W")
        self.assertEqual(value.state_class, "measurement")

    def test_negative_power_is_supported(self) -> None:
        frame = entry(bytes([1, 0, 16, 7, 0, 255]), 27, 0, -350, signed=True)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.value, -350)

    def test_phase_power_aliases_are_collapsed(self) -> None:
        frame = (
            entry(bytes([1, 0, 21, 7, 0, 255]), 27, 0, 100)
            + entry(bytes([1, 0, 36, 7, 0, 255]), 27, 0, 101)
        )
        values = sml_obis.decode_obis_values(frame)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].key, "power_l1")
        self.assertEqual(values[0].value, 100)

    def test_power_factor_has_device_class(self) -> None:
        frame = entry(bytes([1, 0, 13, 7, 0, 255]), 255, -3, 987)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.key, "power_factor")
        self.assertAlmostEqual(value.value, 0.987)
        self.assertEqual(value.device_class, "power_factor")

    def test_unknown_obis_is_preserved(self) -> None:
        frame = entry(bytes([1, 0, 96, 50, 1, 255]), 27, 0, 7)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.obis, "1-0:96.50.1*255")
        self.assertTrue(value.key.startswith("obis_"))
        self.assertFalse(value.known)

    def test_malformed_entry_is_ignored(self) -> None:
        self.assertEqual(sml_obis.decode_obis_values(b"\x07\x01\x00"), [])


if __name__ == "__main__":
    unittest.main()
