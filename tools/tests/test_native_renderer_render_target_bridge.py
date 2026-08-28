import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererRenderTargetBridgeContractTests(unittest.TestCase):
    def test_preview_and_native_test_compile_bridge(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(
            cmake.count("src/native_renderer/render_target_bridge.cpp"), 3
        )
        self.assertIn("pinyon_shift_render_target_bridge_tests EXCLUDE_FROM_ALL", cmake)

    def test_pool_key_covers_exact_host_allocation_contract(self):
        header = (
            ROOT / "src/native_renderer/render_target_bridge.h"
        ).read_text(encoding="utf-8")
        for field in ("host_format", "width", "height", "sample_count", "usage"):
            self.assertIn(field, header)
        self.assertRegex(
            header, r"bool operator==\(const NativeRenderTargetKey\s*&\)"
        )

    def test_gpu_output_never_falls_through_without_a_valid_bridge(self):
        header = (
            ROOT / "src/native_renderer/render_target_bridge.h"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "src/native_renderer/render_target_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("kBridgeRequired", header)
        self.assertIn("known_gpu_outputs_", header)
        self.assertIn("known_gpu_output", source)
        self.assertIn("NativeProducerLookupState::kBridgeRequired", source)
        self.assertIn("RecordGpuOutput", header)
        self.assertIn("known_output_overflow_", header)
        self.assertIn("kKnownGpuOutputLimit", header)

    def test_observed_backend_resources_have_explicit_import_ownership(self):
        header = (
            ROOT / "src/native_renderer/render_target_bridge.h"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "src/native_renderer/texture_resource_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("ImportObserved", header)
        self.assertIn("SetNativeResolveObserver(&ObserveNativeResolve)", source)
        self.assertIn("render_target_bridge_.RecordGpuOutput", source)
        self.assertIn("render_target_bridge_.PublishResolve", source)
        self.assertIn("guest_row_pitch_bytes", source)
        self.assertIn("kProducerResourceLimit", source)
        self.assertIn("kProducerByteLimit", source)
        self.assertIn("producer_deduplications_", source)
        self.assertIn("PruneProducers", source)
        self.assertIn("RetireProducer", source)
        self.assertIn("existing->second.destination != *base", source)
        self.assertIn('RecordFailureOnce("producer_retire_failed")', source)
        self.assertIn('"xenos_resolve", "preserved"', source)
        self.assertNotIn("SetDrawSuppression", source)

    def test_pool_reuse_and_retirement_are_submission_safe(self):
        source = (
            ROOT / "src/native_renderer/render_target_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("available_after_submission <=", source)
        self.assertIn("!target.mapping_pins", source)
        self.assertIn("retire_after_submission > completed_submission", source)
        self.assertNotIn("delete ", source)
        self.assertNotIn("Release()", source)


if __name__ == "__main__":
    unittest.main()
