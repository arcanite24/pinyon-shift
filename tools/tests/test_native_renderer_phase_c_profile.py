import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class NativeRendererPhaseCProfileTests(unittest.TestCase):
    def test_profile_arms_compatible_phase_c_gates(self):
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[switch]$PhaseCQualification", capture)
        block = capture.split("if ($PhaseCQualification) {", 1)[1].split(
            "if (-not $StateRoot)", 1
        )[0]
        self.assertIn("$Scene = 'open_world_day'", block)
        self.assertIn("$ContinuousWorldWorkset = $true", block)
        self.assertIn("$ContinuousTrackWorld = $true", block)
        self.assertIn("$ContinuousStaticWorld = $true", block)
        self.assertIn("$VehicleDrawCorrelation = $true", block)
        self.assertNotIn("$ShadowDepthBatch = $true", block)
        self.assertNotIn("$VehicleResourceContribution", block)

    def test_documented_profile_uses_appdata_state_root(self):
        document = (
            ROOT / "docs/native-renderer/C1_C2_BATCH_QUALIFICATION.md"
        ).read_text(encoding="utf-8")
        self.assertIn("-PhaseCQualification -Json", document)
        self.assertIn(".local\\preview", document)
        self.assertIn("passive C4 player/material joins", document)
        self.assertIn("mutually exclusive", document)


if __name__ == "__main__":
    unittest.main()
