from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "src" / "powergateway.py"
SPEC = importlib.util.spec_from_file_location("powergateway", MODULE_PATH)
assert SPEC and SPEC.loader
powergateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(powergateway)


class SmlFrameTests(unittest.TestCase):
    def test_extracts_frame_from_fragmented_stream(self) -> None:
        frame = powergateway.SML_START + b"payload" + powergateway.SML_END + b"\x00\x12\x34"
        chunks = iter([b"noise" + frame[:5], frame[5:12], frame[12:]])
        self.assertEqual(list(powergateway.iter_sml_frames(chunks)), [frame])

    def test_extracts_multiple_frames(self) -> None:
        frame1 = powergateway.SML_START + b"one" + powergateway.SML_END + b"\x00\x00\x01"
        frame2 = powergateway.SML_START + b"two" + powergateway.SML_END + b"\x00\x00\x02"
        self.assertEqual(list(powergateway.iter_sml_frames(iter([frame1 + frame2]))), [frame1, frame2])


class BufferTests(unittest.TestCase):
    def test_queue_add_remove_and_trim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            buffer = powergateway.MessageBuffer(str(Path(directory) / "buffer.db"))
            buffer.add("a", "1")
            buffer.add("b", "2")
            self.assertEqual(buffer.count(), 2)
            first = buffer.pending(1)[0]
            buffer.remove(first[0])
            self.assertEqual(buffer.count(), 1)
            buffer.add("c", "3")
            buffer.trim(1)
            self.assertEqual(buffer.count(), 1)


if __name__ == "__main__":
    unittest.main()
