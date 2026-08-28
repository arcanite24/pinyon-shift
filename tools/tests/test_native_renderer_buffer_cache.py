import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererBufferCacheContractTests(unittest.TestCase):
    def test_preview_and_native_test_compile_cache(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/buffer_cache.cpp"), 3)
        self.assertIn("pinyon_shift_buffer_cache_tests EXCLUDE_FROM_ALL", cmake)

    def test_invalidation_uses_deferred_collection(self):
        header = (ROOT / "src/native_renderer/buffer_cache.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/buffer_cache.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("RetireInvalidated", header)
        self.assertIn("retire_after_submission", header)
        self.assertIn("resource.retire_after_submission > completed_submission", source)
        self.assertIn("std::max(resource.last_use_submission, current_submission)", source)
        self.assertNotIn("delete ", source)
        self.assertNotIn("Release()", source)

    def test_cache_exposes_required_lifetime_telemetry(self):
        header = (ROOT / "src/native_renderer/buffer_cache.h").read_text(
            encoding="utf-8"
        )
        for field in (
            "hits",
            "misses",
            "invalidations",
            "live_count",
            "live_bytes",
            "retired_count",
            "retired_bytes",
        ):
            self.assertIn(f"uint64_t {field}", header)


if __name__ == "__main__":
    unittest.main()
