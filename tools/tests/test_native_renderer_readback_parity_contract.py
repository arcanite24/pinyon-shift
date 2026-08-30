import pathlib
import unittest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCANNER = REPOSITORY_ROOT / "src" / "native_renderer" / "graphics_hooks.cpp"


class NativeRendererReadbackParityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scanner = SCANNER.read_text(encoding="utf-8")

    def test_exact_comparison_waits_for_all_six_artifacts(self):
        self.assertIn("CompareIsolatedArtifactFiles", self.scanner)
        self.assertIn("kExpectedArtifacts = 6", self.scanner)
        self.assertEqual(
            2,
            self.scanner.count("NotifyIsolatedReadbackArtifactCommitted();"),
        )
        self.assertIn(
            '"native_renderer.isolated_draw.parity_summary"', self.scanner
        )

    def test_summary_covers_color_seed_effect_and_post_draw_parity(self):
        for field in (
            '"color_post_exact"',
            '"depth_seed_exact"',
            '"depth_seed_depth_exact"',
            '"depth_seed_stencil_exact"',
            '"depth_seed_depth_mismatch_bytes"',
            '"depth_seed_stencil_mismatch_bytes"',
            '"depth_post_exact"',
            '"depth_post_depth_exact"',
            '"depth_post_stencil_exact"',
            '"depth_post_depth_mismatch_bytes"',
            '"depth_post_stencil_mismatch_bytes"',
            '"native_depth_effect_bytes"',
            '"native_depth_effect_depth_bytes"',
            '"native_depth_effect_stencil_bytes"',
            '"xenos_depth_effect_bytes"',
            '"xenos_depth_effect_depth_bytes"',
            '"xenos_depth_effect_stencil_bytes"',
            '"draw_effect_exact"',
            '"draw_effect_mismatch_bytes"',
            '"draw_effect_depth_mismatch_bytes"',
            '"draw_effect_stencil_mismatch_bytes"',
            '"draw_effect_first_mismatch"',
            '"stencil_seed_probe_enabled"',
            '"stencil_seed_probe_value"',
        ):
            self.assertIn(field, self.scanner)
        self.assertIn(
            "asynchronous_artifact_exact_depth_stencil_effects", self.scanner
        )
        self.assertIn('{"result_gate", "post_draw_output"}', self.scanner)
        self.assertIn('{"seed_status", seed.exact()', self.scanner)
        self.assertIn(
            '{"draw_effect_status",\n        draw_effect.exact()',
            self.scanner,
        )
        self.assertIn(
            "complete && color.exact() && post.exact()", self.scanner
        )
        self.assertNotIn(
            "complete && color.exact() && seed.exact() && post.exact()",
            self.scanner,
        )

    def test_depth_stencil_tuple_comparison_classifies_each_lane(self):
        self.assertIn("depth_mismatch_bytes", self.scanner)
        self.assertIn("stencil_mismatch_bytes", self.scanner)
        self.assertIn("tuple_byte < 4", self.scanner)
        self.assertGreaterEqual(
            self.scanner.count("CompareIsolatedArtifactFiles("), 6
        )

    def test_draw_effect_comparison_uses_change_masks_and_post_values(self):
        self.assertIn("CompareIsolatedArtifactEffects", self.scanner)
        self.assertIn("native_changed == xenos_changed", self.scanner)
        self.assertIn(
            "native_post_chunk[index] == xenos_post_chunk[index]",
            self.scanner,
        )
        self.assertIn(
            '"draw_effect_exact", draw_effect.exact()', self.scanner
        )
        self.assertNotIn(
            '"draw_effect_exact", seed.exact() && post.exact()', self.scanner
        )

    def test_summary_remains_diagnostic_only(self):
        start = self.scanner.index("void EmitIsolatedReadbackParitySummary()")
        end = self.scanner.index(
            "void NotifyIsolatedReadbackArtifactCommitted()", start
        )
        summary = self.scanner[start:end]
        self.assertIn('{"output_authority", "xenos"}', summary)
        self.assertIn('{"xenos_draw", "preserved"}', summary)
        self.assertIn('{"draw_suppression", "false"}', summary)
        self.assertIn('{"suppression_eligible", "false"}', summary)
        self.assertNotIn("SetDrawSuppression", summary)
        self.assertNotIn("AwaitAllQueueOperationsCompletion", summary)


if __name__ == "__main__":
    unittest.main()
