import unittest

from meter_sources import TasmotaMqttSource, nested_value


class MeterSourceTests(unittest.TestCase):
    def test_nested_value_reads_tasmota_payload(self):
        payload = {"Home": {"Power_curr": 245, "total_in": 41222.86}}
        self.assertEqual(nested_value(payload, "Home.Power_curr"), 245)
        self.assertEqual(nested_value(payload, "Home.total_in"), 41222.86)
        self.assertIsNone(nested_value(payload, "Home.missing"))

    def test_tasmota_default_mapping(self):
        source = TasmotaMqttSource({"host": "localhost"})
        values = source.parse_payload(
            {"Time": "2026-07-21T19:22:38", "Home": {"Power_curr": 244, "total_in": 41222.86}}
        )
        self.assertEqual(values, {"power_total": 244, "energy_import": 41222.86})

    def test_tasmota_custom_mapping(self):
        source = TasmotaMqttSource(
            {
                "host": "localhost",
                "power_path": "Meter.Leistung",
                "energy_import_path": "Meter.Bezug",
                "energy_export_path": "Meter.Einspeisung",
            }
        )
        values = source.parse_payload(
            {"Meter": {"Leistung": -850, "Bezug": 1200.5, "Einspeisung": 321.4}}
        )
        self.assertEqual(
            values,
            {"power_total": -850, "energy_import": 1200.5, "energy_export": 321.4},
        )


if __name__ == "__main__":
    unittest.main()
