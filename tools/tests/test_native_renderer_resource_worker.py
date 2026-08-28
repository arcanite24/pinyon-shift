import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererResourceWorkerContractTests(unittest.TestCase):
    def test_preview_and_native_test_compile_worker(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/resource_worker.cpp"), 3)
        self.assertIn("pinyon_shift_resource_worker_tests EXCLUDE_FROM_ALL", cmake)

    def test_worker_is_bounded_priority_ordered_and_cpu_only(self):
        header = (ROOT / "src/native_renderer/resource_worker.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/resource_worker.cpp").read_text(
            encoding="utf-8"
        )
        for priority in (
            "kVisibleMiss",
            "kLoadingPrewarm",
            "kStreamingPrewarm",
            "kSpeculative",
        ):
            self.assertIn(priority, header)
        self.assertIn("pending_count", header)
        self.assertIn("pending_bytes", header)
        self.assertIn("prepared_count", header)
        self.assertIn("prepared_bytes", header)
        self.assertIn("state_count", header)
        self.assertIn("std::jthread", header)
        self.assertIn("std::stop_token", header)
        self.assertIn("DrainCommits", header)
        self.assertIn("SelectWorstPendingLocked", source)
        self.assertIn("state_evictions", source)
        self.assertNotIn("ID3D12", header + source)
        self.assertNotIn("VkDevice", header + source)

    def test_stale_results_and_lifecycle_are_explicit(self):
        header = (ROOT / "src/native_renderer/resource_worker.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/resource_worker.cpp").read_text(
            encoding="utf-8"
        )
        native_test = (
            ROOT / "tests/native_renderer/resource_worker_test.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("latest_generation_", header)
        self.assertIn("committed_generation_", header)
        self.assertIn("stale_results", header)
        self.assertIn("request_stop", source)
        self.assertIn("committed_generation == 2", native_test)
        self.assertIn("active_workers", native_test)

    def test_texture_observer_uses_cpu_prepare_and_bounded_render_commit(self):
        bridge = (
            ROOT / "src/native_renderer/texture_resource_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("PrepareTextureMetadata", bridge)
        self.assertIn("prewarm_worker_.Submit", bridge)
        self.assertIn("prewarm_worker_.DrainCommits", bridge)
        self.assertIn("prewarm_worker_.Stop", bridge)
        self.assertIn("64 * 1024", bridge)
        self.assertIn('"prewarm_refusals"', bridge)
        self.assertNotIn("SetDrawSuppression", bridge)


if __name__ == "__main__":
    unittest.main()
