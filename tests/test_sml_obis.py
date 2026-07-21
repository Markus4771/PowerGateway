from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "src" / "sml_obis.py"
SPEC = importlib.util.spec_from_file_location("sml_obis", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def entry(obis: bytes, unit: int, scaler: int, value: int) -> bytes:
    return (
        b"\x77"                 # list with seven fields
        + b"\x07" + obis        # OBIS octet string
        + b"\x01"               # optional status
        + b"\x01"               # optional value time
        + b"\x62" + bytes([unit])
        + b"\x52" + int(scaler).to_bytes(1, "big", signed=True)
        + b"\x65" + int(value).to_bytes(4, "big", signed=False)
        + b"\x01"               # optional signature
    )


class ObisDecoderTests(unittest.TestCase):
    def test_import_energy_is_converted_to_kwh(self) -> None:
        frame = entry(bytes([1, 0, 1, 8, 0, 255]), 30, -1, 123456)
        values = MODULE.decode_obis_values(frame)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].key, "energy_import")
        self.assertEqual(values[0].unit, "kWh")
        self.assertAlmostEqual(values[0].value, 12.3456)
        self.assertEqual(values[0].device_class, "energy")

    def test_total_power(self) -> None:
        frame = entry(bytes([1, 0, 16, 7, 0, 255]), 27, 0, 824)
        value = MODULE.decode_obis_values(frame)[0]
        self.assertEqual(value.key, "power_total")
        self.assertEqual(value.value, 824)
        self.assertEqual(value.unit, "W")
        self.assertEqual(value.state_class, "measurement")

    def test_unknown_obis_is_preserved(self) -> None:
        frame = entry(bytes([1, 0, 96, 50, 1, 255]), 27, 0, 7)
        value = MODULE.decode_obis_values(frame)[0]
        self.assertEqual(value.obis, "1-0:96.50.1*255")
        self.assertTrue(value.key.startswith("obis_"))


if __name__ == "__main__":
    unittest.main()
