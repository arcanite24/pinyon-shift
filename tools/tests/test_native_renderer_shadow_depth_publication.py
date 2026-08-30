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
        self.assertIn("bool depth_only_target = false", patch)
        self.assertIn("!result.color_published", hooks)
        self.assertNotIn("SetDrawSuppression", hooks + patch)
        self.assertNotIn("SetCopySuppression", hooks + patch)
        self.assertIn("[switch]$PublishShadowDepth", capture)
        self.assertIn("PublishShadowDepth requires ShadowDepthBatch", capture)


if __name__ == "__main__":
    unittest.main()
