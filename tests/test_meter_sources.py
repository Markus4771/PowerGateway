from meter_sources import TasmotaMqttSource, nested_value


def test_nested_value_reads_tasmota_payload():
    payload = {"Home": {"Power_curr": 245, "total_in": 41222.86}}
    assert nested_value(payload, "Home.Power_curr") == 245
    assert nested_value(payload, "Home.total_in") == 41222.86
    assert nested_value(payload, "Home.missing") is None


def test_tasmota_default_mapping():
    source = TasmotaMqttSource({"host": "localhost"})
    values = source.parse_payload(
        {"Time": "2026-07-21T19:22:38", "Home": {"Power_curr": 244, "total_in": 41222.86}}
    )
    assert values == {"power_total": 244, "energy_import": 41222.86}


def test_tasmota_custom_mapping():
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
    assert values == {
        "power_total": -850,
        "energy_import": 1200.5,
        "energy_export": 321.4,
    }
