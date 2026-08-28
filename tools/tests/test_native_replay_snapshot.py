import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "validate-native-replay-snapshot.py"
SPEC = importlib.util.spec_from_file_location("validate_native_replay_snapshot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SIGNATURE = "747837906D0BF484"


def safe() -> dict:
    return {
        "native_upload": False,
        "native_draw": False,
        "suppression_allowed": False,
        "xenos_authority": True,
    }


class NativeReplaySnapshotTests(unittest.TestCase):
    def make_fixture(self, root: Path):
        payloads = {
            "index.bin": b"index payload",
            "vertex.bin": b"vertex payload data",
            "texture_00_base.bin": b"texture zero",
            "texture_02_base.bin": b"texture two!",
        }
        for name, payload in payloads.items():
            (root / name).write_bytes(payload)

        snapshot = {
            "schema": "pinyon-shift.native-replay-snapshot.v1",
            "candidate_signature": SIGNATURE,
            "frame": 2847,
            "draw": 116,
            "shaders": {
                "vertex": "E35520B6FDEA8C91",
                "pixel": "676B6C2D37982AD9",
                "vertex_specialization": "0000000000000003",
                "pixel_specialization": "0000400000000003",
            },
            "prepared_pipeline_hash": "464D06471DC459EA",
            "geometry": {
                "index": {
                    "file": "index.bin",
                    "bytes": len(payloads["index.bin"]),
                    "hash": MODULE.fnv1a64(payloads["index.bin"]),
                    "format": 1,
                    "endianness": 2,
                    "count": 9300,
                },
                "vertex": {
                    "file": "vertex.bin",
                    "bytes": len(payloads["vertex.bin"]),
                    "hash": MODULE.fnv1a64(payloads["vertex.bin"]),
                    "stride_words": 8,
                },
            },
            "textures": [
                {
                    "fetch_constant": fetch,
                    "base_file": name,
                    "base_bytes": len(payloads[name]),
                    "base_hash": MODULE.fnv1a64(payloads[name]),
                    "mip_file": None,
                    "mip_bytes": 0,
                    "mip_hash": None,
                }
                for fetch, name in ((0, "texture_00_base.bin"), (2, "texture_02_base.bin"))
            ],
            "constants": {
                "texture_states": [{"fetch_constant": 0}, {"fetch_constant": 2}]
            },
            "safety": {"guest_payload_read": "bounded_snapshot_only", **safe()},
        }
        (root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

        geometry = {
            "candidate_signature": SIGNATURE,
            "index_count": {"maximum_observed": 9300},
            "index": {"format": 1, "endianness": 2},
            "binding": {"size_bytes": len(payloads["vertex.bin"]), "stride_bytes": 32},
            "bounds": {"validated": True},
            "safety": safe(),
        }
        draw_state = {"candidate_signature": SIGNATURE, "safety": safe()}
        texture = {
            "candidate_signature": SIGNATURE,
            "resources": [
                {
                    "fetch_constant": fetch,
                    "base_bytes": len(payloads[name]),
                    "base_hash": MODULE.fnv1a64(payloads[name]),
                    "mip_bytes": 0,
                    "mip_hash": "",
                }
                for fetch, name in ((0, "texture_00_base.bin"), (2, "texture_02_base.bin"))
            ],
            "qualification": {"content_stable_across_captures": True},
            "safety": safe(),
        }
        pso = {
            "candidate_signature": SIGNATURE,
            "pso_key": {
                "vertex_shader": snapshot["shaders"]["vertex"],
                "pixel_shader": snapshot["shaders"]["pixel"],
                "vertex_specialization_mask": snapshot["shaders"]["vertex_specialization"],
                "pixel_specialization_mask": snapshot["shaders"]["pixel_specialization"],
                "prepared_pipeline_hash": snapshot["prepared_pipeline_hash"],
            },
            "support": {"ready_for_pso_creation": True},
            "safety": safe(),
        }
        return geometry, draw_state, texture, pso

    def test_valid_snapshot_advances_only_to_isolated_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contracts = self.make_fixture(root)
            result = MODULE.validate_snapshot(root, *contracts)
            self.assertTrue(result["ready_for_isolated_upload"])
            self.assertFalse(result["native_draw"])
            self.assertFalse(result["suppression_allowed"])
            self.assertTrue(result["xenos_authority"])

    def test_payload_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contracts = self.make_fixture(root)
            (root / "index.bin").write_bytes(b"INDEX PAYLOAD")
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                MODULE.validate_snapshot(root, *contracts)

    def test_unsafe_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            geometry, draw_state, texture, pso = self.make_fixture(root)
            pso["safety"]["native_draw"] = True
            with self.assertRaisesRegex(ValueError, "native drawing disabled"):
                MODULE.validate_snapshot(root, geometry, draw_state, texture, pso)

    def test_payload_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contracts = self.make_fixture(root)
            snapshot = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
            snapshot["geometry"]["index"]["file"] = "../index.bin"
            (root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe snapshot payload path"):
                MODULE.validate_snapshot(root, *contracts)


if __name__ == "__main__":
    unittest.main()
