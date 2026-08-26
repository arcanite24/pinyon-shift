import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class SoakEpicContractTests(unittest.TestCase):
    def test_release_builds_suppress_per_frame_viz_query_logging(self):
        patch = (
            ROOT / "patches/rexglue/0034-suppress-high-volume-viz-query-logging.patch"
        ).read_text(encoding="utf-8")
        self.assertIn('-    REXGPU_INFO("Begin viz query ID {:02X}", id);', patch)
        self.assertIn('-    REXGPU_INFO("End viz query ID {:02X}", id);', patch)

    def test_release_reentry_tracing_is_explicitly_opt_in(self):
        patch = (ROOT / "patches/rexglue/0033-gate-high-volume-reentry-tracing.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("PINYON_SHIFT_REENTRY_TRACE", patch)
        self.assertIn("M4_TRACE reentry.tracing enabled=1", patch)
        self.assertIn("if (IsReentryTraceEnabled())", patch)
        self.assertIn("continue_reentry && IsReentryTraceEnabled()", patch)
        self.assertIn("LogMissingReentryStackContinuations", patch)

    def test_release_builds_capture_session_performance_counters(self):
        cmake = (ROOT / "cmake/PinyonShiftRexGlue.cmake").read_text(encoding="utf-8")
        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        self.assertIn("add_compile_definitions(REXGLUE_ENABLE_PERF_COUNTERS)", cmake)
        self.assertIn("pinyon_shift_capture_performance, true", app)
        self.assertIn('SessionId() + ".perf.csv"', app)
        self.assertIn("rex::perf::SetCsvLogPath(perf_csv)", app)

    def test_geometry_repairs_normalize_the_relocated_entry(self):
        hooks = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        self.assertGreaterEqual(hooks.count("StoreGuestU8(r29.u32 + 9u, 0u);"), 2)
        self.assertIn("StoreGuestU8(r29.u32 + 8u, 0u);", hooks)
        self.assertGreaterEqual(hooks.count('"entry_count_zeroed"'), 3)

    def test_build_provenance_reaches_runtime_diagnostics(self):
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        build = (ROOT / "tools/build-preview.ps1").read_text(encoding="utf-8")
        diagnostics = (ROOT / "src/pinyon_shift_diagnostics.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("config/source-provenance.json", package)
        for field in (
            "pinyon_shift_commit",
            "pinyon_shift_dirty",
            "pinyon_shift_source_payload_sha256",
            "rexglue_commit",
            "rexglue_patch_set_sha256",
            "rexglue_patch_count",
            "executable_sha256",
        ):
            self.assertIn(field, build)
            self.assertIn(field, diagnostics)
        self.assertIn("pinyon_shift_build.json", build)
        self.assertIn("pinyon_shift_build.json", diagnostics)


if __name__ == "__main__":
    unittest.main()
