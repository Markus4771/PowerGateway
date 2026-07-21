from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from simulator import PROFILES, SimulatedSerial, SmlSimulator  # noqa: E402
from sml_obis import decode_obis_values  # noqa: E402


class SimulatorTests(unittest.TestCase):
    def test_all_profiles_create_parseable_frames(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                simulator = SmlSimulator(profile=profile, interval=0.1, seed=4771)
                frame = simulator.frame()
                values = decode_obis_values(frame)
                keys = {value.key for value in values}
                self.assertIn("energy_import", keys)
                self.assertIn("power_total", keys)
                self.assertTrue(frame.startswith(bytes.fromhex("1b1b1b1b01010101")))

    def test_solar_profile_can_publish_signed_power(self) -> None:
        simulator = SmlSimulator(profile="solar", interval=0.1, seed=4771)
        simulator.started -= 90
        values = decode_obis_values(simulator.frame())
        total = next(value for value in values if value.key == "power_total")
        self.assertIsInstance(total.value, (int, float))

    def test_unknown_profile_preserves_unknown_obis(self) -> None:
        simulator = SmlSimulator(profile="unknown", interval=0.1, seed=4771)
        values = decode_obis_values(simulator.frame())
        self.assertTrue(any(value.obis == "1-0:96.50.1*255" for value in values))

    def test_simulated_serial_behaves_like_serial_stream(self) -> None:
        stream = SimulatedSerial(SmlSimulator(profile="generic", interval=0.1, seed=1))
        chunk = stream.read(64)
        self.assertTrue(chunk)
        self.assertTrue(stream.is_open)
        stream.close()
        self.assertFalse(stream.is_open)
        self.assertEqual(stream.read(64), b"")

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SmlSimulator(profile="does-not-exist")


if __name__ == "__main__":
    unittest.main()
