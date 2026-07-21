#!/usr/bin/env python3
"""Decode a captured SML telegram from a file or hexadecimal input."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sml_obis import decode_obis_values  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PowerGateway SML-Telegramm dekodieren")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Binärdatei mit einem SML-Telegramm")
    group.add_argument("--hex", dest="hex_data", help="SML-Telegramm als Hexadezimaltext")
    args = parser.parse_args()

    if args.file:
        frame = args.file.read_bytes()
    else:
        try:
            frame = bytes.fromhex("".join(str(args.hex_data).split()))
        except ValueError as exc:
            parser.error(f"Ungültige Hex-Daten: {exc}")

    measurements = [item.to_dict() for item in decode_obis_values(frame)]
    print(json.dumps({"bytes": len(frame), "measurements": measurements}, indent=2, ensure_ascii=False))
    return 0 if measurements else 2


if __name__ == "__main__":
    raise SystemExit(main())
