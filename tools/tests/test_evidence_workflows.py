import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

visual = module("visual_baseline", ROOT / "tools/visual-baseline.py")
qualification = module("qualification_session", ROOT / "tools/qualification-session.py")
renderer = module("renderer_ab", ROOT / "tools/renderer-ab.py")

def png(path, width=2, height=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\0" + b"\0\0\0" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))

class EvidenceWorkflowTests(unittest.TestCase):
    def test_visual_session_requires_all_labeled_pngs_and_builds_sheet(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "pinyon_shift.exe"; executable.write_bytes(b"exact-build")
            session = visual.create_session(Path(temp), executable)
            with self.assertRaises(ValueError): visual.validate(session)
            for scene in visual.SCENES: png(session / "captures" / f"{scene}.png")
            self.assertEqual([], visual.validate(session)["missing"])
            sheet = visual.contact_sheet(session)
            self.assertTrue(sheet.is_file()); self.assertIn("open-world-night", sheet.read_text())

    def test_qualification_enforces_marker_order_and_safe_extensions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); build = root / "build.json"; build.write_text('{"commit":"abc"}')
            session = qualification.start(root / "sessions", build)
            with self.assertRaises(ValueError): qualification.mark(session, "race", None)
            for name in qualification.MARKERS: qualification.mark(session, name, None)
            evidence = root / "events.jsonl"; evidence.write_text("{}\n")
            self.assertTrue(qualification.package(session, [evidence]).is_file())
            unsafe = root / "dump.dmp"; unsafe.write_bytes(b"private")
            with self.assertRaises(ValueError): qualification.package(session, [unsafe])

    def test_renderer_ab_requires_memexport_counters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fingerprint = root / "build.json"; fingerprint.write_text('{"commit":"abc"}')
            session = renderer.prepare(root, "readback_memexport", fingerprint)
            summary = {"frame_time_us": {"median": 1000, "p95": 1200}}
            for variant in ("control", "candidate"):
                (session / variant / "performance-summary.json").write_text(json.dumps(summary))
                (session / variant / "visual-validation.json").write_text('{"missing":[]}')
            with self.assertRaises(ValueError): renderer.compare(session)
            summary["memexport_counters"] = {name: 0 for name in renderer.MEMEXPORT_COUNTERS}
            for variant in ("control", "candidate"):
                (session / variant / "performance-summary.json").write_text(json.dumps(summary))
            self.assertEqual("readback_memexport", renderer.compare(session)["variable"])

    def test_renderer_ab_requires_resolve_counters_and_supports_full(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fingerprint = root / "build.json"; fingerprint.write_text('{"commit":"abc"}')
            session = renderer.prepare(root, "readback_resolve", fingerprint, "full")
            manifest = json.loads((session / "manifest.json").read_text())
            self.assertEqual("full", manifest["variants"][1]["value"])
            summary = {"frames": {"frame_time_us": {"median": 1000, "p95": 1200}}}
            for variant in ("control", "candidate"):
                (session / variant / "performance-summary.json").write_text(json.dumps(summary))
                (session / variant / "visual-validation.json").write_text('{"missing":[]}')
            with self.assertRaises(ValueError): renderer.compare(session)
            summary["resolve_readback_counters"] = {name: 0 for name in renderer.RESOLVE_COUNTERS}
            for variant in ("control", "candidate"):
                (session / variant / "performance-summary.json").write_text(json.dumps(summary))
            self.assertEqual("readback_resolve", renderer.compare(session)["variable"])

if __name__ == "__main__": unittest.main()
