import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "compare-native-renderer-pass-readbacks.py"
SPEC = importlib.util.spec_from_file_location("native_pass_readbacks", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_readback(root: Path, role: str, data: bytes, *, row_pitch: int = 8) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-draw-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "source": {
            "width": 1,
            "height": 1,
            "row_pitch": row_pitch,
            "dxgi_format": 10,
            "bytes": len(data),
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


def write_depth_readback(root: Path, role: str, data: bytes) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-depth-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "capture_content": "depth_stencil",
        "source": {
            "width": 1,
            "height": 2,
            "dxgi_format": 19,
            "sample_count": 1,
            "encoding": "d3d12_texture_planes",
            "bytes": len(data),
            "planes": [
                {
                    "index": 0,
                    "offset": 0,
                    "row_pitch": 8,
                    "row_size": 4,
                    "row_count": 2,
                },
                {
                    "index": 1,
                    "offset": 16,
                    "row_pitch": 4,
                    "row_size": 1,
                    "row_count": 2,
                },
            ],
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


def write_msaa_depth_readback(
    root: Path,
    role: str,
    data: bytes,
    *,
    stencil_seed_probe: bool | None = None,
) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-depth-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "capture_content": "depth_stencil",
        "source": {
            "width": 2,
            "height": 2,
            "dxgi_format": 19,
            "sample_count": 2,
            "encoding": "depth32_stencil8_sample_tuples",
            "bytes": len(data),
            "planes": [
                {
                    "index": 0,
                    "offset": 0,
                    "row_pitch": 32,
                    "row_size": 32,
                    "row_count": 2,
                }
            ],
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    if stencil_seed_probe is not None:
        metadata["diagnostic"] = {
            "stencil_seed_probe": stencil_seed_probe,
            "stencil_seed_probe_value": 0xA5,
        }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


class NativeRendererPassReadbackTests(unittest.TestCase):
    def test_exact_active_bytes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes(range(8)))
            report = MODULE.compare(native, xenos)
            self.assertEqual(report["result"], "pass")
            self.assertTrue(report["metrics"]["exact_active_bytes"])
            self.assertFalse(report["safety"]["suppression_allowed"])

    def test_padding_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)) + b"\x00" * 8, row_pitch=16)
            write_readback(xenos, "xenos", bytes(range(8)) + b"\xFF" * 8, row_pitch=16)
            self.assertEqual(MODULE.compare(native, xenos)["result"], "pass")

    def test_active_difference_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes([99]) + bytes(range(1, 8)))
            report = MODULE.compare(native, xenos)
            self.assertEqual(report["result"], "fail")
            self.assertEqual(report["metrics"]["different_bytes"], 1)

    def test_mismatched_frame_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes(range(8)))
            metadata_path = xenos / "readback.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["frame"] += 1
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frame values differ"):
                MODULE.compare(native, xenos)

    def test_exact_depth_and_stencil_planes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            data = bytes(range(21))
            write_depth_readback(native, "native", data)
            write_depth_readback(xenos, "xenos", data)
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")
            self.assertEqual(report["scope"]["content"], "depth-stencil")
            self.assertEqual(report["metrics"]["compared_bytes"], 10)
            components = report["metrics"]["components"]
            self.assertTrue(components["depth"]["exact_active_bytes"])
            self.assertTrue(components["stencil"]["exact_active_bytes"])

    def test_depth_padding_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytearray(range(21))
            xenos_data = bytearray(native_data)
            for index in (4, 5, 6, 7, 12, 13, 14, 15, 17, 18, 19):
                xenos_data[index] = 255
            write_depth_readback(native, "native", bytes(native_data))
            write_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")

    def test_stencil_difference_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytes(range(21))
            xenos_data = bytearray(native_data)
            xenos_data[20] ^= 0xFF
            write_depth_readback(native, "native", native_data)
            write_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "fail")
            self.assertEqual(report["metrics"]["different_bytes"], 1)
            components = report["metrics"]["components"]
            self.assertTrue(components["depth"]["exact_active_bytes"])
            self.assertEqual(components["stencil"]["different_bytes"], 1)

    def test_exact_msaa_depth_sample_tuples_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            data = bytes(range(64))
            write_msaa_depth_readback(native, "native", data)
            write_msaa_depth_readback(xenos, "xenos", data)
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")
            self.assertEqual(report["metrics"]["compared_bytes"], 64)
            self.assertEqual(report["layout"]["sample_count"], 2)
            components = report["metrics"]["components"]
            self.assertTrue(components["exact_depth"])
            self.assertTrue(components["exact_stencil"])
            self.assertEqual(components["changed_samples"], 0)

    def test_msaa_depth_and_stencil_deltas_are_classified(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytes(64)
            xenos_data = bytearray(native_data)
            xenos_data[0] = 1
            xenos_data[28] = 2
            write_msaa_depth_readback(native, "native", native_data)
            write_msaa_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            components = report["metrics"]["components"]
            self.assertFalse(components["exact_depth"])
            self.assertFalse(components["exact_stencil"])
            self.assertEqual(components["depth_tuple_changes"], 1)
            self.assertEqual(components["stencil_tuple_changes"], 1)
            self.assertEqual(components["depth_different_bytes"], 1)
            self.assertEqual(components["stencil_different_bytes"], 1)
            self.assertEqual(components["changed_samples"], 2)
            self.assertEqual(components["changed_sample_histogram"], [1, 1])
            self.assertEqual(
                components["changed_bounds"],
                {"left": 0, "top": 0, "right": 1, "bottom": 0},
            )
            self.assertEqual(len(components["first_changed_samples"]), 2)

    def test_depth_checkpoints_localize_draw_effect_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            seed = bytes(64)
            native_after = bytearray(seed)
            native_after[4] = 129
            write_msaa_depth_readback(native_seed, "native_seed", seed)
            write_msaa_depth_readback(xenos_seed, "xenos_seed", seed)
            write_msaa_depth_readback(native, "native", bytes(native_after))
            write_msaa_depth_readback(xenos, "xenos", seed)

            report = MODULE.compare_depth_checkpoints(
                native, xenos, native_seed, xenos_seed
            )

            self.assertEqual(
                report["schema"],
                "pinyon-shift.native-renderer-depth-checkpoint-analysis.v2",
            )
            self.assertEqual(report["result"], "fail")
            self.assertEqual(report["diagnosis"], "draw_effect_divergence")
            self.assertEqual(
                report["comparisons"]["seed_copy"]["result"], "pass"
            )
            self.assertEqual(
                report["comparisons"]["draw_effect_parity"]["result"],
                "fail",
            )
            native_components = report["comparisons"]["native_draw_effect"][
                "metrics"
            ]["components"]
            self.assertTrue(native_components["exact_depth"])
            self.assertFalse(native_components["exact_stencil"])

    def test_depth_checkpoints_identify_seed_copy_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            seed = bytes(64)
            bad_seed = bytearray(seed)
            bad_seed[4] = 7
            write_msaa_depth_readback(
                native_seed, "native_seed", bytes(bad_seed)
            )
            write_msaa_depth_readback(xenos_seed, "xenos_seed", seed)
            write_msaa_depth_readback(native, "native", bytes(bad_seed))
            write_msaa_depth_readback(xenos, "xenos", seed)

            report = MODULE.compare_depth_checkpoints(
                native, xenos, native_seed, xenos_seed
            )

            self.assertEqual(
                report["diagnosis"],
                "seed_divergence_with_exact_draw_effect",
            )
            effect = report["comparisons"]["draw_effect_parity"]
            self.assertEqual(effect["result"], "pass")
            self.assertTrue(effect["metrics"]["exact_draw_effect"])
            self.assertEqual(effect["metrics"]["mismatch_bytes"], 0)

    def test_depth_effect_parity_requires_matching_changed_post_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            seed = bytes(64)
            native_after = bytearray(seed)
            xenos_after = bytearray(seed)
            native_after[4] = 7
            xenos_after[4] = 9
            write_msaa_depth_readback(native_seed, "native_seed", seed)
            write_msaa_depth_readback(xenos_seed, "xenos_seed", seed)
            write_msaa_depth_readback(native, "native", bytes(native_after))
            write_msaa_depth_readback(xenos, "xenos", bytes(xenos_after))

            report = MODULE.compare_depth_checkpoints(
                native, xenos, native_seed, xenos_seed
            )

            effect = report["comparisons"]["draw_effect_parity"]
            self.assertEqual(effect["result"], "fail")
            self.assertEqual(effect["metrics"]["mismatch_bytes"], 1)
            self.assertEqual(effect["metrics"]["depth_mismatch_bytes"], 0)
            self.assertEqual(effect["metrics"]["stencil_mismatch_bytes"], 1)
            self.assertEqual(
                effect["metrics"]["first_mismatches"][0]["component"],
                "stencil",
            )

    def test_stencil_seed_probe_confirms_copy_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            guest = bytes(64)
            private = bytearray(guest)
            private[4] = 0xA5
            for path, role, data in (
                (native_seed, "native_seed", bytes(private)),
                (xenos_seed, "xenos_seed", guest),
                (native, "native", bytes(private)),
                (xenos, "xenos", guest),
            ):
                write_msaa_depth_readback(
                    path, role, data, stencil_seed_probe=True
                )

            report = MODULE.compare_depth_checkpoints(
                native, xenos, native_seed, xenos_seed
            )

            self.assertEqual(
                report["diagnosis"], "stencil_copy_omission_confirmed"
            )
            probe = report["stencil_seed_probe"]
            self.assertEqual(probe["sentinel_survivors"], 1)
            self.assertEqual(
                probe["evidence"], "sentinel_survived_guest_copy"
            )
            self.assertEqual(probe["inspected_stencil_values"], 8)

    def test_stencil_seed_probe_preserves_existing_diagnosis_when_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            guest = bytes(64)
            private = bytearray(guest)
            private[4] = 7
            for path, role, data in (
                (native_seed, "native_seed", bytes(private)),
                (xenos_seed, "xenos_seed", guest),
                (native, "native", bytes(private)),
                (xenos, "xenos", guest),
            ):
                write_msaa_depth_readback(
                    path, role, data, stencil_seed_probe=True
                )

            report = MODULE.compare_depth_checkpoints(
                native, xenos, native_seed, xenos_seed
            )

            self.assertEqual(
                report["diagnosis"],
                "seed_divergence_with_exact_draw_effect",
            )
            self.assertEqual(
                report["stencil_seed_probe"]["sentinel_survivors"], 0
            )
            self.assertEqual(
                report["stencil_seed_probe"]["evidence"],
                "sentinel_overwritten",
            )

    def test_stencil_seed_probe_rejects_inconsistent_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_seed = root / "pass.depth.seed.native"
            xenos_seed = root / "pass.depth.seed.xenos"
            native = root / "pass.depth"
            xenos = root / "pass.depth.xenos"
            for path, role in (
                (native_seed, "native_seed"),
                (xenos_seed, "xenos_seed"),
                (native, "native"),
            ):
                write_msaa_depth_readback(
                    path, role, bytes(64), stencil_seed_probe=True
                )
            write_msaa_depth_readback(xenos, "xenos", bytes(64))

            with self.assertRaisesRegex(
                ValueError, "stencil seed probe metadata is inconsistent"
            ):
                MODULE.compare_depth_checkpoints(
                    native, xenos, native_seed, xenos_seed
                )


if __name__ == "__main__":
    unittest.main()
