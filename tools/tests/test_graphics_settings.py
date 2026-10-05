import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/set-graphics-experiment.ps1"
POWERSHELL = shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class GraphicsSettingsTests(unittest.TestCase):
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
                "-PresentationFps", "30",
                "-RenderFps", "120",
                "-Preset", "experimental_2x",
                "-DisableMotionBlur", "true",
                "-DisableDepthOfField", "true",
            )
            updated = config.read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["anisotropy"], 16)
            self.assertIn("pinyon_shift_config_schema = 27", updated)
            self.assertIn('gpu_backend = "vulkan"', updated)
            self.assertIn("gpu_record_thread = true", updated)
            self.assertNotIn("fh1_renderer", updated)
            self.assertNotIn("renderer", result["settings"])
            self.assertIn("xma_relaxed_padding_admission = false", updated)
            self.assertNotIn("occlusion_query", result["settings"])
            self.assertEqual(result["settings"]["host_present_fps_limit"], 30)
            self.assertEqual(result["settings"]["fh1_render_fps_limit"], 120)
            self.assertIn("pinyon_shift_fh1_render_fps_limit = 120", updated)
            self.assertTrue(result["settings"]["host_present_sleep_spin"])
            self.assertTrue(result["settings"]["disable_motion_blur"])
            self.assertTrue(result["settings"]["disable_depth_of_field"])
            self.assertIn("custom_value = 77", updated)
            self.assertIn("draw_resolution_scale_x = 2", updated)
            self.assertEqual(result["settings"]["preset"], "experimental_2x")
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())
            self.run_tool(state, "-Action", "Restore")
            self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_saving_the_scale_keeps_in_game_settings(self):
        # The launcher only saves the resolution scale; everything else is
        # set in game and must survive.
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "pinyon_shift_config_schema = 25\nanisotropic_override = 5\n"
                "swap_post_effect = \"fxaa\"\nvsync = false\n"
                "pinyon_shift_fh1_render_fps_limit = 30\nhost_present_fps_limit = 120\n"
                "disable_motion_blur = true\n",
                encoding="utf-8")
            result = self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "3")
            updated = config.read_text(encoding="utf-8")
            for line in ("anisotropic_override = 5", 'swap_post_effect = "fxaa"', "vsync = false",
                         "pinyon_shift_fh1_render_fps_limit = 30",
                         "host_present_fps_limit = 120", "disable_motion_blur = true",
                         "draw_resolution_scale_x = 3", "draw_resolution_scale_y = 3"):
                self.assertIn(line, updated)
            self.assertEqual(result["settings"]["resolution_scale"], 3)
            self.assertFalse(result["settings"]["vsync"])

    def test_apply_turns_page_state_clearing_off_from_schema_25(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 25\nclear_memory_page_state = true\n",
                              encoding="utf-8")
            result = self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "1")
            text = config.read_text(encoding="utf-8")
            self.assertIn("pinyon_shift_config_schema = 27", text)
            self.assertIn("clear_memory_page_state = false", text)
            self.assertFalse(result["settings"]["clear_memory_page_state"])
            # Once on schema 26, a player who turns it back on keeps it.
            config.write_text("pinyon_shift_config_schema = 26\nclear_memory_page_state = true\n",
                              encoding="utf-8")
            self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "1")
            self.assertIn("clear_memory_page_state = true", config.read_text(encoding="utf-8"))

    def test_apply_moves_earlier_schemas_to_vulkan_once(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            # The old QUALITY 60 preset wrote "any" (Direct3D 12) without the split.
            config.write_text('pinyon_shift_config_schema = 26\ngpu_backend = "any"\n'
                              "gpu_record_thread = false\n", encoding="utf-8")
            self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "1")
            text = config.read_text(encoding="utf-8")
            self.assertIn('gpu_backend = "vulkan"', text)
            self.assertIn("gpu_record_thread = true", text)
            # A player who then picks Direct3D 12 keeps it.
            config.write_text('pinyon_shift_config_schema = 27\ngpu_backend = "d3d12"\n'
                              "gpu_record_thread = false\n", encoding="utf-8")
            self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "1")
            text = config.read_text(encoding="utf-8")
            self.assertIn('gpu_backend = "d3d12"', text)
            self.assertIn("gpu_record_thread = false", text)

    def test_graphics_api_choice_sets_backend_and_record_thread(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 27\nanisotropic_override = 5\n",
                              encoding="utf-8")
            self.assertEqual(self.run_tool(state, "-Action", "Get")["settings"]["graphics_api"],
                             "vulkan")
            result = self.run_tool(state, "-Action", "Apply", "-GraphicsApi", "d3d12")
            text = config.read_text(encoding="utf-8")
            self.assertIn('gpu_backend = "d3d12"', text)
            self.assertIn("gpu_record_thread = false", text)
            self.assertIn("anisotropic_override = 5", text)
            self.assertEqual(result["settings"]["graphics_api"], "d3d12")
            result = self.run_tool(state, "-Action", "Apply", "-GraphicsApi", "vulkan")
            text = config.read_text(encoding="utf-8")
            self.assertIn('gpu_backend = "vulkan"', text)
            self.assertIn("gpu_record_thread = true", text)
            self.assertEqual(result["settings"]["graphics_api"], "vulkan")

    def test_output_scaling_sets_present_effect_and_reports_the_window(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 27\nfullscreen = false\n"
                              "window_width = 1920\nwindow_height = 1080\n", encoding="utf-8")
            settings = self.run_tool(state, "-Action", "Get")["settings"]
            self.assertEqual(settings["output_scaling"], "bilinear")
            self.assertFalse(settings["fullscreen"])
            self.assertEqual((settings["window_width"], settings["window_height"]), (1920, 1080))
            self.assertTrue(settings["letterbox"])
            result = self.run_tool(state, "-Action", "Apply", "-OutputScaling", "fsr")
            self.assertIn('present_effect = "fsr"', config.read_text(encoding="utf-8"))
            self.assertEqual(result["settings"]["output_scaling"], "fsr")
            # Saving other choices keeps the in-game one.
            self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "2")
            self.assertIn('present_effect = "fsr"', config.read_text(encoding="utf-8"))

    def test_treasure_map_is_on_unless_the_file_turns_it_off(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 27\n", encoding="utf-8")
            self.assertTrue(self.run_tool(state, "-Action", "Get")["settings"]["treasure_map"])
            result = self.run_tool(state, "-Action", "Apply", "-TreasureMap", "false")
            self.assertIn("pinyon_shift_dlc_treasure_map = false", config.read_text(encoding="utf-8"))
            self.assertFalse(result["settings"]["treasure_map"])

    def test_post_effect_defaults_and_explicit_choices(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            for action in ("Get", "Apply"):
                settings = self.run_tool(state, "-Action", action)["settings"]
                self.assertTrue(settings["disable_motion_blur"])
                self.assertTrue(settings["disable_depth_of_field"])
            config = state / "config/pinyon_shift.toml"
            config.write_text("pinyon_shift_config_schema = 27\n", encoding="utf-8")
            settings = self.run_tool(state, "-Action", "Get")["settings"]
            self.assertTrue(settings["disable_motion_blur"])
            self.assertTrue(settings["disable_depth_of_field"])
            self.run_tool(state, "-Action", "Apply", "-DisableMotionBlur", "false",
                          "-DisableDepthOfField", "false")
            settings = self.run_tool(state, "-Action", "Apply", "-ResolutionScale", "2")["settings"]
            self.assertFalse(settings["disable_motion_blur"])
            self.assertFalse(settings["disable_depth_of_field"])

    def test_reset_writes_supported_defaults_and_preserves_backup(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 5\nswap_post_effect = \"fxaa\"\n", encoding="utf-8")
            result = self.run_tool(state, "-Action", "Reset")
            text = config.read_text(encoding="utf-8")
            self.assertIn("swap_post_effect = \"none\"", text)
            self.assertIn("disable_motion_blur = true", text)
            self.assertIn("disable_depth_of_field = true", text)
            self.assertIn("draw_resolution_scale_x = 1", text)
            self.assertIn("xma_relaxed_padding_admission = false", text)
            self.assertNotIn('occlusion_query', text)
            self.assertNotIn('zpd_end', text)
            self.assertNotIn('readback_resolve', text)
            self.assertIn('clear_memory_page_state = false', text)
            self.assertIn('host_present_fps_limit = 0', text)
            self.assertIn('host_present_sleep_spin = true', text)
            self.assertIn('pinyon_shift_fh1_render_fps_limit = 0', text)
            self.assertIn('pinyon_shift_fh1_source_presentation = true', text)
            self.assertIn("pinyon_shift_config_schema = 27", text)
            self.assertIn('gpu_backend = "vulkan"', text)
            self.assertIn("gpu_record_thread = true", text)
            self.assertNotIn("fh1_renderer", text)
            self.assertEqual(result["settings"]["preset"], "shipping_1x")
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())

    def test_apply_replaces_legacy_guest_vblank_with_render_limit(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "pinyon_shift_config_schema = 15\n"
                "pinyon_shift_fh1_guest_vblank_hz = 240\n"
                "pinyon_shift_native_renderer_texture_bridge = true\n"
                'pinyon_shift_native_renderer = "diagnostic_triangle"\n'
                "pinyon_shift_native_renderer_sky_horizon_suppression = true\n"
                "pinyon_shift_fh1_native_v4 = false\n",
                encoding="utf-8",
            )
            self.run_tool(state, "-Action", "Apply")
            text = config.read_text(encoding="utf-8")
            self.assertNotIn("pinyon_shift_fh1_guest_vblank_hz", text)
            self.assertNotIn("pinyon_shift_native_renderer_texture_bridge", text)
            self.assertNotIn("pinyon_shift_native_renderer =", text)
            self.assertNotIn("pinyon_shift_native_renderer_sky_horizon_suppression", text)
            self.assertNotIn("pinyon_shift_fh1_native_v4", text)
            self.assertIn("pinyon_shift_fh1_render_fps_limit = 0", text)

    def test_apply_removes_retired_renderer_settings(self):
        # Schema 24 retires the renderer choice and the Xenos-era and
        # native-shadow renderer settings the runtime no longer registers.
        retired = (
            'fh1_renderer = "xenos"',
            "fh1_native_shadow = true",
            'fh1_native_shadow_dump_dir = "dumps"',
            "fh1_native_shadow_dump_frames = 4",
            "fh1_native_shadow_verify = true",
            "fh1_native_shadow_verify_draws = 8",
            "fh1_discovery_sampling = true",
            "fh1_owned_depth_clear = true",
            "fh1_owned_depth_tile_clear = true",
            "fh1_native_reflection_mips = true",
            "fh1_mip_decode_probe = true",
            "fh1_native_ui_boundary_probe = true",
            "fh1_glow_probe = true",
            "fh1_recycle_geometry_buffers = true",
            "fh1_contain_geometry_windows = true",
            "fh1_cache_geometry_rejections = true",
            "fh1_geometry_cache_mb = 256",
            "native_stencil_value_output = true",
            "native_stencil_value_output_d3d12_intel = true",
            "pinyon_shift_native_renderer_census = false",
            # Schema 25: one occlusion-query path.
            'occlusion_query = "strict"',
            'zpd_end_policy = "report_layout"',
            'zpd_end_fallback = "pairwise_sentinel"',
        )
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "pinyon_shift_config_schema = 23\n" + "\n".join(retired) + "\ncustom_value = 77\n",
                encoding="utf-8",
            )
            result = self.run_tool(state, "-Action", "Apply")
            text = config.read_text(encoding="utf-8")
            self.assertIn("pinyon_shift_config_schema = 27", text)
            self.assertIn("custom_value = 77", text)
            for line in retired:
                self.assertNotIn(line.split(" =")[0] + " =", text)
            self.assertNotIn("renderer", result["settings"])

    def test_renderer_can_no_longer_be_selected(self):
        tool = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("$Renderer", tool)
        self.assertNotIn("'xenos'", tool)
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            completed = subprocess.run(
                [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(TOOL), "-StateRoot", temporary, "-Action", "Apply",
                 "-Renderer", "xenos", "-Json"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((pathlib.Path(temporary) / "config/pinyon_shift.toml").exists())

    def test_get_accepts_schema_25(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 25\nvsync = true\n", encoding="utf-8")
            result = self.run_tool(state, "-Action", "Get")
            self.assertEqual(result["operation"], "get")

    def test_experimental_3x_writes_4k_class_scale(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            result = self.run_tool(
                state, "-Action", "Apply", "-Preset", "experimental_3x"
            )
            text = (state / "config/pinyon_shift.toml").read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["preset"], "experimental_3x")
            self.assertEqual(result["settings"]["resolution_scale"], 3)
            self.assertIn("draw_resolution_scale_x = 3", text)

    def test_apply_removes_retired_resolve_settings(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "pinyon_shift_config_schema = 19\n"
                "readback_resolve = \"full\"\n"
                "readback_resolve_half_pixel_offset = true\n",
                encoding="utf-8",
            )
            result = self.run_tool(state, "-Action", "Apply")
            text = config.read_text(encoding="utf-8")
            self.assertEqual(result["settings"]["preset"], "shipping_1x")
            self.assertNotIn("readback_resolve", text)
            self.assertTrue(pathlib.Path(result["backup_path"]).is_file())

    def test_apply_keeps_developer_resolve_readback_on_current_schema(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-settings-") as temporary:
            state = pathlib.Path(temporary)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                "pinyon_shift_config_schema = 25\nreadback_resolve = \"full\"\n", encoding="utf-8"
            )
            self.run_tool(state, "-Action", "Apply")
            self.assertIn('readback_resolve = "full"', config.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
