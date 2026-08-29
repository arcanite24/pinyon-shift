import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/set-graphics-experiment.ps1"
QUALIFY_ZPD = ROOT / "tools/qualify-zpd.ps1"
QUALIFY_RESOLVE = ROOT / "tools/qualify-resolve.ps1"
POWERSHELL = shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class GraphicsSettingsTests(unittest.TestCase):
    def test_resolve_qualification_plan_covers_presets_and_scenes(self):
        completed = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(QUALIFY_RESOLVE), "-Action", "Plan", "-Json"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(
            [item["preset"] for item in plan["profiles"]],
            ["shipping_1x", "experimental_2x", "experimental_3x", "accurate_showroom"],
        )
        self.assertEqual(len(plan["candidate_scenes"]), 8)

    def test_zpd_qualification_plan_covers_required_matrix(self):
        completed = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(QUALIFY_ZPD), "-Action", "Plan", "-Json"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(len(plan["matrix"]), 6)
        self.assertEqual(plan["admission"]["required_cold_boots"], 10)
        self.assertEqual(plan["matrix"][2]["label"], "fast-layout")

    def run_tool(self, state, *arguments):
        completed = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(TOOL), "-StateRoot", str(state), *arguments, "-Json"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_apply_migrates_schema_and_restore_recovers_previous_file(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            original = "pinyon_shift_config_schema = 1\nmnk_mode = true\ncustom_value = 77\n"
            config.write_text(original, encoding="utf-8")
            result = self.run_tool(
                state, "-Action", "Apply", "-Anisotropy", "16",
                "-PostEffect", "fxaa", "-ResolutionScale", "2",
                "-OcclusionQuery", "fast",
                "-ZpdEndPolicy", "pairwise_sentinel",
                "-ZpdEndFallback", "none",
                "-PresentationFps", "30",
                "-Preset", "experimental_2x",
                "-DisableMotionBlur", "true",
                "-DisableDepthOfField", "true",
                "-NativeRenderer", "diagnostic_triangle",
            )
            updated = config.read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["anisotropy"], 16)
            self.assertIn("pinyon_shift_config_schema = 11", updated)
            self.assertIn("xma_relaxed_padding_admission = false", updated)
            self.assertEqual(result["settings"]["occlusion_query"], "fast")
            self.assertIn('occlusion_query = "fast"', updated)
            self.assertEqual(result["settings"]["zpd_end_policy"], "pairwise_sentinel")
            self.assertEqual(result["settings"]["zpd_end_fallback"], "none")
            self.assertEqual(result["settings"]["host_present_fps_limit"], 30)
            self.assertTrue(result["settings"]["host_present_sleep_spin"])
            self.assertTrue(result["settings"]["disable_motion_blur"])
            self.assertTrue(result["settings"]["disable_depth_of_field"])
            self.assertEqual(result["settings"]["native_renderer"], "diagnostic_triangle")
            self.assertIn('pinyon_shift_native_renderer = "diagnostic_triangle"', updated)
            self.assertIn("custom_value = 77", updated)
            self.assertIn("draw_resolution_scale_x = 2", updated)
            self.assertEqual(result["settings"]["preset"], "experimental_2x")
            self.assertEqual(result["settings"]["readback_resolve"], "fast")
            self.assertTrue(result["settings"]["readback_resolve_half_pixel_offset"])
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())
            self.run_tool(state, "-Action", "Restore")
            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_reset_writes_supported_defaults_and_preserves_backup(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 5\nswap_post_effect = \"fxaa\"\n", encoding="utf-8")
            result = self.run_tool(state, "-Action", "Reset")
            text = config.read_text(encoding="utf-8")
            self.assertIn("swap_post_effect = \"none\"", text)
            self.assertIn("disable_motion_blur = false", text)
            self.assertIn("disable_depth_of_field = false", text)
            self.assertIn("draw_resolution_scale_x = 1", text)
            self.assertIn("xma_relaxed_padding_admission = false", text)
            self.assertIn('occlusion_query = "legacy"', text)
            self.assertIn('zpd_end_policy = "report_layout"', text)
            self.assertIn('zpd_end_fallback = "pairwise_sentinel"', text)
            self.assertIn('readback_resolve = "none"', text)
            self.assertIn('readback_resolve_half_pixel_offset = false', text)
            self.assertIn('clear_memory_page_state = true', text)
            self.assertIn('host_present_fps_limit = 60', text)
            self.assertIn('host_present_sleep_spin = true', text)
            self.assertIn('pinyon_shift_native_renderer = "xenos"', text)
            self.assertEqual(result["settings"]["preset"], "shipping_1x")
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())

    def test_reset_renderer_preserves_other_settings(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'pinyon_shift_config_schema = 11\n'
                'pinyon_shift_native_renderer = "diagnostic_triangle"\n'
                'pinyon_shift_native_renderer_sky_horizon_suppression = true\n'
                'custom_value = 77\n',
                encoding="utf-8",
            )
            result = self.run_tool(state, "-Action", "ResetRenderer")
            text = config.read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["native_renderer"], "xenos")
            self.assertFalse(result["settings"]["sky_horizon_suppression"])
            self.assertIn('pinyon_shift_native_renderer = "xenos"', text)
            self.assertIn("custom_value = 77", text)
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())

    def test_set_renderer_selects_comparison_without_changing_other_settings(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'pinyon_shift_config_schema = 11\n'
                'pinyon_shift_native_renderer = "xenos"\n'
                'custom_value = 77\n',
                encoding="utf-8",
            )
            result = self.run_tool(
                state,
                "-Action",
                "SetRenderer",
                "-NativeRenderer",
                "comparison_native",
            )
            text = config.read_text(encoding="utf-8")
            self.assertEqual(
                result["settings"]["native_renderer"], "comparison_native"
            )
            self.assertIn(
                'pinyon_shift_native_renderer = "comparison_native"', text
            )
            self.assertIn("custom_value = 77", text)
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())

    def test_family_suppression_control_is_restart_gated_and_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            enabled = self.run_tool(
                state, "-Action", "SetSkyHorizonSuppression",
                "-SkyHorizonSuppression", "true",
            )
            self.assertTrue(enabled["settings"]["sky_horizon_suppression"])
            self.assertTrue(enabled["restart_required"])
            disabled = self.run_tool(
                state, "-Action", "SetSkyHorizonSuppression",
                "-SkyHorizonSuppression", "false",
            )
            self.assertFalse(disabled["settings"]["sky_horizon_suppression"])

    def test_experimental_3x_writes_4k_class_scale_with_fast_readback(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            result = self.run_tool(
                state, "-Action", "Apply", "-Preset", "experimental_3x"
            )
            text = (state / "config/pinyon_shift.toml").read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["preset"], "experimental_3x")
            self.assertEqual(result["settings"]["resolution_scale"], 3)
            self.assertEqual(result["settings"]["readback_resolve"], "fast")
            self.assertTrue(result["settings"]["readback_resolve_half_pixel_offset"])
            self.assertIn("draw_resolution_scale_x = 3", text)

    def test_accurate_showroom_is_explicit_and_preserves_backup(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 9\nreadback_resolve = \"none\"\n", encoding="utf-8")
            result = self.run_tool(state, "-Action", "Apply", "-Preset", "accurate_showroom")
            text = config.read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["preset"], "accurate_showroom")
            self.assertEqual(result["settings"]["readback_resolve"], "full")
            self.assertIn('readback_resolve = "full"', text)
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
