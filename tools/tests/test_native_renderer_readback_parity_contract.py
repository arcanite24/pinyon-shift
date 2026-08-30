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
            '"depth_post_exact"',
            '"native_depth_effect_bytes"',
            '"xenos_depth_effect_bytes"',
            '"draw_effect_exact"',
        ):
            self.assertIn(field, self.scanner)
        self.assertIn("asynchronous_artifact_exact_bytes", self.scanner)

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
