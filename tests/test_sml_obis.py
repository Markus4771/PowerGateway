from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import sml_obis  # noqa: E402


def entry(obis: bytes, unit: int, scaler: int, value: int) -> bytes:
    return (
        b"\x77"
        + b"\x07" + obis
        + b"\x01"
        + b"\x01"
        + b"\x62" + bytes([unit])
        + b"\x52" + int(scaler).to_bytes(1, "big", signed=True)
        + b"\x65" + int(value).to_bytes(4, "big", signed=False)
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

    def test_total_power(self) -> None:
        frame = entry(bytes([1, 0, 16, 7, 0, 255]), 27, 0, 824)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.key, "power_total")
        self.assertEqual(value.value, 824)
        self.assertEqual(value.unit, "W")
        self.assertEqual(value.state_class, "measurement")

    def test_unknown_obis_is_preserved(self) -> None:
        frame = entry(bytes([1, 0, 96, 50, 1, 255]), 27, 0, 7)
        value = sml_obis.decode_obis_values(frame)[0]
        self.assertEqual(value.obis, "1-0:96.50.1*255")
        self.assertTrue(value.key.startswith("obis_"))


if __name__ == "__main__":
    unittest.main()
