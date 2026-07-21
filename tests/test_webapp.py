from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import webapp  # noqa: E402


class WebAppTests(unittest.TestCase):
    def test_parse_timestamp_accepts_utc_z_suffix(self) -> None:
        parsed = webapp.parse_timestamp("2026-07-21T12:34:56Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_parse_timestamp_rejects_invalid_value(self) -> None:
        self.assertIsNone(webapp.parse_timestamp("kein-zeitstempel"))
        self.assertIsNone(webapp.parse_timestamp(None))

    def test_public_config_masks_credentials(self) -> None:
        original = webapp.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.toml"
                path.write_text(
                    "[mqtt]\nusername='meter'\npassword='geheim'\ntoken='abc'\n"
                    "[gateway]\nname='test-gateway'\n",
                    encoding="utf-8",
                )
                webapp.CONFIG_PATH = path
                config = webapp.public_config()
                self.assertEqual(config["mqtt"]["username"], "meter")
                self.assertEqual(config["mqtt"]["password"], "********")
                self.assertEqual(config["mqtt"]["token"], "********")
                self.assertEqual(config["gateway"]["name"], "test-gateway")
        finally:
            webapp.CONFIG_PATH = original

    def test_overview_is_read_only_and_reports_stale_values(self) -> None:
        original_data = webapp.DATA_DIR
        original_config = webapp.CONFIG_PATH
        original_version = webapp.VERSION_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "status.json").write_text(json.dumps({"meter_connected": True}), encoding="utf-8")
                (root / "latest_values.json").write_text(
                    json.dumps({"received_at": "2020-01-01T00:00:00+00:00", "measurements": []}),
                    encoding="utf-8",
                )
                config = root / "config.toml"
                config.write_text("[gateway]\nname='test'\n[web]\nstale_after_seconds=30\n[mqtt]\nenabled=false\n", encoding="utf-8")
                version = root / "version.txt"
                version.write_text("0.6.0-dev\n", encoding="utf-8")
                webapp.DATA_DIR = root
                webapp.CONFIG_PATH = config
                webapp.VERSION_PATH = version
                response = webapp.app.test_client().get("/_internal/overview")
                payload = response.get_json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload["version"], "0.6.0-dev")
                self.assertTrue(payload["values_stale"])
                self.assertFalse(payload["mqtt_enabled"])
        finally:
            webapp.DATA_DIR = original_data
            webapp.CONFIG_PATH = original_config
            webapp.VERSION_PATH = original_version


if __name__ == "__main__":
    unittest.main()
