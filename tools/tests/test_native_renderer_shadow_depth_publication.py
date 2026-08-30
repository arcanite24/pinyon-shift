import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ShadowDepthPublicationContractTests(unittest.TestCase):
    def test_compute_handoff_export_is_payload_free_and_exact(self):
        exporter = (
            ROOT / "tools/export-native-renderer-compute-handoff.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "tools/export-native-renderer-compute-handoff.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("GetReadOnlyResources(rd.ShaderStage.Compute, True)", exporter)
        self.assertIn("GetReadWriteResources(rd.ShaderStage.Compute, True)", exporter)
        self.assertIn("descriptor.byteOffset", exporter)
        self.assertIn('"resource_payload_exported": False', exporter)
        self.assertIn('"shader_payload_exported": False', exporter)
        self.assertIn('"publication_allowed": False', exporter)
        self.assertIn("Get-AuthenticodeSignature", wrapper)
        self.assertIn("must be below $localRoot", wrapper)

    def test_depth_publication_keeps_every_xenos_stage(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0092-d3d12-depth-only-isolated-publication.patch"
        ).read_text(encoding="utf-8")
        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_SHADOW_DEPTH_PUBLICATION", hooks
        )
        self.assertIn("CompleteIsolatedShadowDepthPublication", hooks)
        self.assertIn("request.suppress_guest_draw_if_published = false", hooks)
        self.assertIn('"consumer_handoff", "xenos_rt_dump_retained"', hooks)
        self.assertIn(
            'kShadowDepthCasterClass = "dynamic_vehicle"', hooks
        )
        self.assertIn(
            'kShadowDepthAtlasRegion = "0,0,2048,2048"', hooks
        )
        self.assertGreaterEqual(
            hooks.count('{"caster_class", kShadowDepthCasterClass}'), 3
        )
        self.assertGreaterEqual(
            hooks.count('{"atlas_region", kShadowDepthAtlasRegion}'), 3
        )
        self.assertIn("bool depth_only_target = false", patch)
        self.assertIn("!result.color_published", hooks)
        self.assertNotIn("SetDrawSuppression", hooks + patch)
        self.assertNotIn("SetCopySuppression", hooks + patch)
        self.assertIn("[switch]$PublishShadowDepth", capture)
        self.assertIn("PublishShadowDepth requires ShadowDepthBatch", capture)

    def test_continuous_depth_publication_fails_closed_without_suppression(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_SHADOW_DEPTH_CONTINUOUS", hooks
        )
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_SHADOW_DEPTH_CONTINUOUS_EPOCH_LIMIT",
            hooks,
        )
        self.assertIn("epoch_limit < 2", hooks)
        self.assertIn("epoch_limit > 120", hooks)
        self.assertIn('"bounded_multi_epoch_complete"', hooks)
        self.assertIn("FailClosedContinuousShadowDepth", hooks)
        self.assertIn('"non_contiguous_epoch"', hooks)
        self.assertIn('"backend_replay_failure"', hooks)
        self.assertIn('"publication_failure"', hooks)
        self.assertIn(
            '"native_renderer.shadow_depth_continuous.fail_closed"', hooks
        )
        self.assertIn('"fallback", "authoritative_xenos_content"', hooks)
        self.assertIn('"draw_suppression", "false"', hooks)
        self.assertIn('"resolve_suppression", "false"', hooks)
        self.assertNotIn("SetDrawSuppression", hooks)
        self.assertNotIn("SetCopySuppression", hooks)
        self.assertIn("[switch]$ContinuousShadowDepth", capture)
        self.assertIn("[int]$ContinuousShadowDepthEpochs = 8", capture)
        self.assertIn(
            "ContinuousShadowDepth requires PublishShadowDepth", capture
        )

    def test_continuous_qualification_verifier_accepts_exact_safe_epochs(self):
        verifier = (
            ROOT / "tools/verify-native-renderer-shadow-depth-continuous.py"
        )
        with tempfile.TemporaryDirectory(prefix="pinyon-shadow-depth-") as root:
            root = Path(root)
            native_dir = root / "native"
            xenos_dir = root / "xenos"
            native_dir.mkdir()
            xenos_dir.mkdir()
            payload = b"paired-depth-stencil"
            (native_dir / "isolated.bin").write_bytes(payload)
            (xenos_dir / "isolated.bin").write_bytes(payload)
            source = {"bytes": len(payload), "hash": "SAME"}
            (native_dir / "readback.json").write_text(
                json.dumps(
                    {
                        "capture_role": "native_batch",
                        "source": source,
                        "safety": {"suppression_allowed": False},
                    }
                ),
                encoding="utf-8",
            )
            (xenos_dir / "readback.json").write_text(
                json.dumps(
                    {
                        "capture_role": "xenos_batch",
                        "source": source,
                        "safety": {"suppression_allowed": False},
                    }
                ),
                encoding="utf-8",
            )
            events = []
            for epoch, frame in enumerate((100, 101), 1):
                events.append(
                    {
                        "event": "native_renderer.shadow_depth_batch.publication",
                        "status": "published_depth_stencil",
                        "ownership_mode": "multi_epoch_fail_closed",
                        "publication_epoch": str(epoch),
                        "frame": str(frame),
                        "color": "not_bound",
                        "consumer_handoff": "xenos_rt_dump_retained",
                        "xenos_producer_draws": "preserved",
                        "xenos_draw_suppression": "false",
                        "resolve_suppression": "false",
                        "suppression_eligible": "false",
                    }
                )
            events.append(
                {
                    "event": "native_renderer.shadow_depth_batch.summary",
                    "status": "bounded_multi_epoch_complete",
                    "ownership_mode": "multi_epoch_fail_closed",
                    "continuous_failed_closed": "false",
                    "continuous_failure_reason": "none",
                    "continuous_limit_reached": "true",
                    "request_accounting_complete": "true",
                    "batch_accounting_complete": "true",
                    "consumer_handoff": "xenos_rt_dump_retained",
                    "xenos_draw": "preserved",
                    "draw_suppression": "false",
                    "suppression_eligible": "false",
                    "batches_started": "2",
                    "batches_completed": "2",
                    "publication_attempts": "2",
                    "publications": "2",
                    "continuous_publication_epochs": "2",
                    "continuous_max_publication_epochs": "2",
                    "continuous_epoch_limit": "2",
                    "requests": "160",
                    "recorded": "160",
                    "batches_interrupted": "0",
                    "backend_failed_batches": "0",
                    "target_creation_failures": "0",
                    "unsupported": "0",
                    "publication_failures": "0",
                }
            )
            log = root / "session.jsonl"
            log.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(verifier),
                    "--log",
                    str(log),
                    "--native-dir",
                    str(native_dir),
                    "--xenos-dir",
                    str(xenos_dir),
                    "--expected-epochs",
                    "2",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "qualified")


if __name__ == "__main__":
    unittest.main()
