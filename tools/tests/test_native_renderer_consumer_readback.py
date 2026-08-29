import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "analyze-native-renderer-consumer-readback.py"
SPEC = importlib.util.spec_from_file_location("consumer_readback", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


FAMILY = (
    "2E5E0A854BE00027/BDFFA72B7ED2FBA4/"
    "000000000000003F/000000000016003F"
)


def write_readback(
    root: Path,
    phase: str,
    payload: bytes,
    *,
    width=2,
    height=1,
    source_sample_count=None,
):
    phase_root = root / phase
    phase_root.mkdir(parents=True)
    metadata = {
        "schema": MODULE.READBACK_SCHEMA,
        "consumer_family": FAMILY,
        "frame": 42,
        "draw": 7,
        "phase": phase,
        "source": {
            "width": width,
            "height": height,
            "row_pitch": len(payload) // height,
            "dxgi_format": 28,
            "bytes_per_pixel": 4,
            "sample_count": 1,
            **(
                {"source_sample_count": source_sample_count}
                if source_sample_count is not None
                else {}
            ),
            "bytes": len(payload),
            "hash": "0000000000000000",
        },
        "payload": {"file": "target.bin"},
        "safety": {
            "output_authority": "xenos",
            "xenos_draw_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "suppression_allowed": False,
        },
    }
    (phase_root / "readback.json").write_text(json.dumps(metadata))
    (phase_root / "target.bin").write_bytes(payload)


def write_depth_readback(
    root: Path,
    phase: str,
    payload: bytes,
    *,
    sample=1,
    width=1,
    height=1,
    sample_count=2,
):
    phase_root = root / "depth" / phase
    phase_root.mkdir(parents=True)
    row_size = width * sample_count * 8
    metadata = {
        "schema": MODULE.READBACK_SCHEMA,
        "consumer_family": FAMILY,
        "frame": 42,
        "draw": 7,
        "sample": sample,
        "attachment": "depth_stencil",
        "phase": phase,
        "source": {
            "width": width,
            "height": height,
            "row_pitch": row_size,
            "dxgi_format": 20,
            "bytes_per_pixel": 0,
            "sample_count": sample_count,
            "plane_count": 1,
            "planes": [
                {
                    "offset": 0,
                    "row_pitch": row_size,
                    "row_size": row_size,
                    "row_count": height,
                }
            ],
            "encoding": "depth32_stencil8_sample_tuples",
            "bytes": len(payload),
            "hash": "0000000000000000",
        },
        "payload": {"file": "target.bin"},
        "safety": {
            "output_authority": "xenos",
            "xenos_draw_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "suppression_allowed": False,
        },
    }
    (phase_root / "readback.json").write_text(json.dumps(metadata))
    (phase_root / "target.bin").write_bytes(payload)


class ConsumerReadbackTests(unittest.TestCase):
    def test_reports_exact_draw_contribution_and_writes_pngs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            output = Path(temporary) / "report"
            write_readback(root, "before", bytes([10, 20, 30, 255, 1, 2, 3, 255]))
            write_readback(root, "after", bytes([10, 25, 30, 255, 1, 2, 3, 255]))

            report = MODULE.analyze(root, output)

            self.assertEqual(MODULE.REPORT_SCHEMA, report["schema"])
            self.assertEqual(FAMILY, report["consumer_family"])
            self.assertEqual(1, report["contribution"]["changed_pixels"])
            self.assertEqual(5, report["contribution"]["maximum_channel_delta"])
            self.assertEqual(
                {"left": 0, "top": 0, "right": 0, "bottom": 0},
                report["contribution"]["bounds"],
            )
            self.assertFalse(report["safety"]["suppression_allowed"])
            for name in ("before.png", "after.png", "difference-4x.png", "changed-mask.png"):
                self.assertTrue((output / name).read_bytes().startswith(b"\x89PNG"))

    def test_ignores_row_padding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            output = Path(temporary) / "report"
            before = bytes([10, 20, 30, 255, 90, 91, 92, 93])
            after = bytes([10, 20, 30, 255, 1, 2, 3, 4])
            write_readback(root, "before", before, width=1)
            write_readback(root, "after", after, width=1)

            report = MODULE.analyze(root, output)

            self.assertEqual(0, report["contribution"]["changed_pixels"])
            self.assertIsNone(report["contribution"]["bounds"])

    def test_accepts_color_resolved_from_msaa_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            color = bytes([10, 20, 30, 255])
            write_readback(
                root, "before", color, width=1, source_sample_count=4
            )
            write_readback(
                root, "after", color, width=1, source_sample_count=4
            )

            report = MODULE.analyze(root, Path(temporary) / "report")

            self.assertEqual(1, report["source"]["sample_count"])
            self.assertEqual(4, report["source"]["source_sample_count"])

    def test_decodes_half_float_color(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            for phase, red in (("before", 0.0), ("after", 1.0)):
                phase_root = root / phase
                phase_root.mkdir(parents=True)
                payload = struct.pack("<eeee", red, 0.5, 0.0, 1.0)
                metadata = {
                    "schema": MODULE.READBACK_SCHEMA,
                    "consumer_family": FAMILY,
                    "frame": 42,
                    "draw": 7,
                    "phase": phase,
                    "source": {
                        "width": 1,
                        "height": 1,
                        "row_pitch": 8,
                        "dxgi_format": 10,
                        "bytes_per_pixel": 8,
                        "bytes": 8,
                        "hash": "0000000000000000",
                    },
                    "payload": {"file": "target.bin"},
                    "safety": {
                        "output_authority": "xenos",
                        "xenos_draw_preserved": True,
                        "draw_suppression": False,
                        "resolve_suppression": False,
                        "suppression_allowed": False,
                    },
                }
                (phase_root / "readback.json").write_text(json.dumps(metadata))
                (phase_root / "target.bin").write_bytes(payload)

            report = MODULE.analyze(root, Path(temporary) / "report")

            self.assertEqual(255, report["contribution"]["maximum_channel_delta"])

    def test_rejects_unsafe_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            payload = bytes([0, 0, 0, 255])
            write_readback(root, "before", payload, width=1)
            write_readback(root, "after", payload, width=1)
            path = root / "after" / "readback.json"
            metadata = json.loads(path.read_text())
            metadata["safety"]["draw_suppression"] = True
            path.write_text(json.dumps(metadata))

            with self.assertRaisesRegex(ValueError, "draw suppression"):
                MODULE.analyze(root, Path(temporary) / "report")

    def test_reports_multisample_depth_and_stencil_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            color = bytes([0, 0, 0, 255])
            write_readback(root, "before", color, width=1)
            write_readback(root, "after", color, width=1)
            before = struct.pack("<fIfI", 0.25, 0, 0.75, 1)
            after = struct.pack("<fIfI", 0.50, 0, 0.75, 2)
            write_depth_readback(root, "before", before)
            write_depth_readback(root, "after", after)

            report = MODULE.analyze(root, Path(temporary) / "report")

            depth = report["attachments"]["depth_stencil"]
            self.assertEqual(1, depth["changed_pixels"])
            self.assertEqual(2, depth["changed_samples"])
            self.assertEqual(1, depth["depth_tuple_changes"])
            self.assertEqual(1, depth["stencil_tuple_changes"])
            self.assertTrue((Path(temporary) / "report" / "depth-before.png").is_file())

    def test_aggregates_contiguous_multi_sample_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            for sample, changed in ((1, False), (2, True)):
                sample_root = root / f"sample-{sample:04d}"
                before_color = bytes([0, 0, 0, 255])
                after_color = bytes([1 if changed else 0, 0, 0, 255])
                write_readback(sample_root, "before", before_color, width=1)
                write_readback(sample_root, "after", after_color, width=1)
                for phase in ("before", "after"):
                    path = sample_root / phase / "readback.json"
                    metadata = json.loads(path.read_text())
                    metadata["sample"] = sample
                    metadata["frame"] = 40 + sample
                    metadata["draw"] = 6 + sample
                    path.write_text(json.dumps(metadata))
                depth = struct.pack("<fIfI", 0.25, 0, 0.75, 1)
                write_depth_readback(sample_root, "before", depth, sample=sample)
                write_depth_readback(sample_root, "after", depth, sample=sample)
                for phase in ("before", "after"):
                    path = sample_root / "depth" / phase / "readback.json"
                    metadata = json.loads(path.read_text())
                    metadata["frame"] = 40 + sample
                    metadata["draw"] = 6 + sample
                    path.write_text(json.dumps(metadata))

            report = MODULE.analyze(root, Path(temporary) / "report")

            self.assertEqual(MODULE.CORPUS_SCHEMA, report["schema"])
            self.assertEqual(2, report["sample_count"])
            self.assertEqual(1, report["aggregate"]["samples_with_color_delta"])
            self.assertFalse(report["aggregate"]["all_samples_no_attachment_delta"])

    def test_rejects_malformed_depth_plane_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            color = bytes([0, 0, 0, 255])
            write_readback(root, "before", color, width=1)
            write_readback(root, "after", color, width=1)
            depth = struct.pack("<fIfI", 0.25, 0, 0.75, 1)
            write_depth_readback(root, "before", depth)
            write_depth_readback(root, "after", depth)
            path = root / "depth" / "after" / "readback.json"
            metadata = json.loads(path.read_text())
            metadata["source"]["planes"][0]["row_size"] = len(depth) + 1
            path.write_text(json.dumps(metadata))

            with self.assertRaisesRegex(ValueError, "depth plane layout"):
                MODULE.analyze(root, Path(temporary) / "report")

    def test_incomplete_corpus_never_claims_no_attachment_delta(self):
        with tempfile.TemporaryDirectory() as temporary:
            sample_root = Path(temporary) / "readback" / "sample-0001"
            color = bytes([0, 0, 0, 255])
            write_readback(sample_root, "before", color, width=1)
            write_readback(sample_root, "after", color, width=1)

            report = MODULE.analyze(
                sample_root.parent, Path(temporary) / "report"
            )

            self.assertFalse(report["aggregate"]["all_samples_complete"])
            self.assertFalse(
                report["aggregate"]["all_samples_no_attachment_delta"]
            )
            self.assertIsNone(report["samples"][0]["attachment_delta"])


if __name__ == "__main__":
    unittest.main()
