import copy
import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "evaluate-native-renderer-suppression.py"
SPEC = importlib.util.spec_from_file_location("native_suppression", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def evidence(status="pass"):
    return {
        "schema": MODULE.INPUT_SCHEMA,
        "family": "sky_horizon",
        "scene": "open_world_day",
        "build_sha256": "A" * 64,
        "signatures": ["747837906D0BF484", "1D253A52B55C9FB3"],
        "gates": {
            name: {
                "status": status,
                "evidence": f"fixture evidence for {name}",
                "artifacts": [],
            }
            for name in MODULE.REQUIRED_GATES
        },
        "safety": {
            "xenos_draws_preserved": True,
            "draw_suppression_implemented": False,
            "resolve_suppression_implemented": False,
        },
    }


class NativeRendererSuppressionAdmissionTests(unittest.TestCase):
    def test_complete_evidence_is_ready_but_never_enables_suppression(self):
        result = MODULE.evaluate(evidence())
        self.assertTrue(result["summary"]["ready_for_suppression_implementation"])
        self.assertEqual(result["summary"]["passed"], len(MODULE.REQUIRED_GATES))
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertFalse(result["safety"]["draw_suppression_implemented"])
        self.assertFalse(result["safety"]["resolve_suppression_implemented"])

    def test_unknown_and_failed_gates_are_explicit_blockers(self):
        document = evidence()
        document["gates"]["color_parity"]["status"] = "fail"
        document["gates"]["guest_cpu_visibility"]["status"] = "unknown"
        result = MODULE.evaluate(document)
        self.assertFalse(result["summary"]["ready_for_suppression_implementation"])
        self.assertEqual(
            [blocker["gate"] for blocker in result["summary"]["blockers"]],
            ["color_parity", "guest_cpu_visibility"],
        )
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_rejects_missing_extra_and_malformed_gates(self):
        missing = evidence()
        del missing["gates"]["depth_parity"]
        with self.assertRaisesRegex(ValueError, "missing gates"):
            MODULE.evaluate(missing)

        extra = evidence()
        extra["gates"]["looks_good"] = {
            "status": "pass", "evidence": "subjective", "artifacts": []
        }
        with self.assertRaisesRegex(ValueError, "unknown gates"):
            MODULE.evaluate(extra)

        malformed = evidence()
        malformed["gates"]["depth_parity"]["status"] = "maybe"
        with self.assertRaisesRegex(ValueError, "invalid status"):
            MODULE.evaluate(malformed)

    def test_rejects_any_claim_that_suppression_is_already_implemented(self):
        for field in (
            "xenos_draws_preserved",
            "draw_suppression_implemented",
            "resolve_suppression_implemented",
        ):
            document = evidence()
            document["safety"][field] = not document["safety"][field]
            with self.assertRaisesRegex(ValueError, f"safety.{field}"):
                MODULE.evaluate(document)

    def test_verifies_local_artifact_hash_and_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "comparison.json"
            artifact.write_bytes(b"qualified")
            digest = hashlib.sha256(b"qualified").hexdigest().upper()
            document = evidence()
            document["gates"]["color_parity"]["artifacts"] = [
                {"path": "comparison.json", "sha256": digest}
            ]
            result = MODULE.evaluate(document, artifact_root=root)
            self.assertTrue(
                result["gates"]["color_parity"]["artifacts"][0]["verified"]
            )

            mismatch = copy.deepcopy(document)
            mismatch["gates"]["color_parity"]["artifacts"][0]["sha256"] = "B" * 64
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                MODULE.evaluate(mismatch, artifact_root=root)

            escape = copy.deepcopy(document)
            escape["gates"]["color_parity"]["artifacts"][0]["path"] = "../outside"
            with self.assertRaisesRegex(ValueError, "escapes artifact root"):
                MODULE.evaluate(escape, artifact_root=root)


if __name__ == "__main__":
    unittest.main()
