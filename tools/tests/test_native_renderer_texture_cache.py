import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererTextureCacheContractTests(unittest.TestCase):
    def test_preview_and_native_test_compile_texture_cache(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/texture_cache.cpp"), 3)
        self.assertIn("pinyon_shift_texture_cache_tests EXCLUDE_FROM_ALL", cmake)

    def test_selected_retained_pass_dxn_contract_is_encoded(self):
        header = (ROOT / "src/native_renderer/texture_cache.h").read_text(
            encoding="utf-8"
        )
        native_test = (
            ROOT / "tests/native_renderer/texture_cache_test.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("kXenosTextureFormatDxn = 49", header)
        for fetch_word in (
            "0x82024002",
            "0x14649071",
            "0x0007E0FF",
            "0x00A80D10",
            "0x00000003",
            "0x00000A00",
        ):
            self.assertIn(fetch_word, native_test)
        self.assertIn("descriptor->width == 256", native_test)
        self.assertIn("descriptor->height == 64", native_test)

    def test_streaming_retry_is_bounded_and_keeps_a_fallback(self):
        header = (ROOT / "src/native_renderer/texture_cache.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/texture_cache.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("maximum_attempts", header)
        self.assertIn("maximum_delay_frames", header)
        self.assertIn("kIncompletePayload", header)
        self.assertIn("serving_previous", header)
        self.assertIn("slot.attempt >= retry_policy_.maximum_attempts", source)
        self.assertIn("slot->live ? slot->live->handle : 0", source)

    def test_invalidation_and_replacement_use_deferred_destruction(self):
        source = (ROOT / "src/native_renderer/texture_cache.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("RetireInvalidated", source)
        self.assertIn("std::max(texture.last_use_submission, current_submission)", source)
        self.assertNotIn("delete ", source)
        self.assertNotIn("Release()", source)

    def test_cache_bounds_resources_and_remembered_state(self):
        header = (ROOT / "src/native_renderer/texture_cache.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/texture_cache.cpp").read_text(
            encoding="utf-8"
        )
        bridge = (
            ROOT / "src/native_renderer/texture_resource_bridge.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "maximum_live_bytes",
            "maximum_live_count",
            "maximum_state_count",
            "maximum_evictions_per_maintenance",
            "normal_idle_frames",
            "pressure_idle_frames",
        ):
            self.assertIn(token, bridge)
        self.assertIn("size_t Trim", header)
        self.assertIn("PruneStateLocked", source)
        self.assertIn("cache_budget_evictions", bridge)
        self.assertIn("cache_budget_refusals", bridge)
        self.assertIn(
            "cache_.Trim(observation.current_submission,", bridge
        )
        self.assertNotIn(
            "cache_.Request(key, observation_count_", bridge
        )


if __name__ == "__main__":
    unittest.main()
