import getpass
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ReleaseContractTests(unittest.TestCase):
    def test_release_workflow_publishes_only_preview_channels_as_prereleases(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("$release.channel -eq 'preview'", workflow)
        self.assertIn("$release.channel -ne 'stable'", workflow)
        self.assertIn("$arguments += '--prerelease'", workflow)
        self.assertNotIn(
            "--generate-notes --prerelease --verify-tag",
            workflow,
        )

    def test_supported_dump_uses_exact_hash_and_size(self):
        data = json.loads((ROOT / "config/supported-dumps.json").read_text())
        self.assertEqual(data["policy"]["match"], "exact_sha256_and_size")
        self.assertEqual(data["policy"]["unknown_dump_action"], "reject")
        for dump in data["dumps"]:
            self.assertGreater(dump["iso"]["size_bytes"], 0)
            self.assertRegex(dump["iso"]["sha256"], r"^[0-9A-F]{64}$")

    def test_downloads_are_https_and_sha256_pinned(self):
        data = json.loads((ROOT / "config/release-toolchain.json").read_text())
        for key in ("git", "xz", "llvm", "extract_xiso"):
            item = data[key]
            self.assertTrue(item["url"].startswith("https://"))
            self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$")
        self.assertTrue(data["visual_studio"]["bootstrap_url"].startswith("https://"))
        self.assertEqual(data["rexglue"]["tag"], "v0.10.0")
        self.assertRegex(data["rexglue"]["base_commit"], r"^[0-9a-f]{40}$")

    def test_rexglue_patches_have_stable_order_and_no_binary_payload(self):
        patches = sorted((ROOT / "patches/rexglue").glob("*.patch"))
        self.assertEqual(len(patches), 55)
        self.assertEqual(
            patches[-1].name,
            "0055-graphics-index-reset-observer.patch",
        )
        self.assertEqual(len(patches), len({path.name[:4] for path in patches}))
        for path in patches:
            text = path.read_text(encoding="utf-8", errors="strict")
            self.assertIn("diff --git", text)
            self.assertNotIn("GIT binary patch", text)

    def test_rexglue_010_version_and_patch_migration_contract(self):
        toolchain = json.loads((ROOT / "config/release-toolchain.json").read_text())
        self.assertEqual(toolchain["rexglue"]["tag"], "v0.10.0")
        self.assertEqual(
            toolchain["rexglue"]["base_commit"],
            "f5337cdc947ff6d4c4196737e2c807a48f2a1fc2",
        )
        manifest = (ROOT / "config/rexglue/pinyon_shift_manifest.toml").read_text()
        integration = (ROOT / "cmake/PinyonShiftRexGlue.cmake").read_text()
        self.assertIn('sdk_version = "0.10.0"', manifest)
        self.assertIn("find_package(rexglue 0.10.0 EXACT", integration)
        self.assertNotIn("ReXGlue SDK 0.9.0", integration)

        dispositions = (ROOT / "config/rexglue/PATCH_DISPOSITIONS.md").read_text()
        for number in range(27):
            self.assertIn(f"`{number:04d}`", dispositions)
        self.assertIn(
            "`0000` Windows migration-test stabilization | Retire", dispositions
        )
        self.assertFalse(
            (ROOT / "patches/rexglue/0000-v0.9-windows-migration-test-stabilization.patch").exists()
        )

    def test_rexglue_codegen_is_dependency_tracked_and_explicitly_cleanable(self):
        build = (ROOT / "tools/build-preview.ps1").read_text()
        integration = (ROOT / "cmake/PinyonShiftRexGlue.cmake").read_text()
        self.assertIn("[switch]$CleanGenerated", build)
        self.assertIn("$requiresBootstrap", build)
        self.assertIn("codegen.build.stamp", build)
        self.assertIn("DEPFILE", integration)
        self.assertIn("-fasync-exceptions", integration)
        self.assertIn("target_precompile_headers", integration)
        self.assertIn("_recomp OBJECT", integration)
        self.assertIn("--ignore-stamp", integration)
        self.assertIn("rexglue-sdk EXCLUDE_FROM_ALL", integration)
        self.assertIn("PINYON_SHIFT_REXGLUE_CODEGEN_DEPENDS", integration)

        package_script = (ROOT / "tools/package-launcher.ps1").read_text()
        self.assertIn("$_.Name -ne 'generated'", package_script)
        self.assertIn("Add-Type -AssemblyName System.IO.Compression\n", package_script)
        self.assertIn("function New-DeterministicZip", package_script)
        self.assertIn("FromUnixTimeSeconds", package_script)

    def test_rexglue_downloads_retry_and_windows_skips_optional_libusb(self):
        prepare = (ROOT / "tools/prepare-rexglue.ps1").read_text(encoding="utf-8")
        build = (ROOT / "tools/build-preview.ps1").read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

        self.assertIn("function Invoke-PinyonGitWithRetry", prepare)
        self.assertIn("$maximumAttempts = 3", prepare)
        self.assertIn("http.version=HTTP/1.1", prepare)
        self.assertIn("submodule', 'update', '--init', '--recursive'", prepare)
        self.assertNotIn("clone --recursive", prepare)
        self.assertIn("-DSDL_HIDAPI_LIBUSB=OFF", build)
        self.assertIn("set(SDL_HIDAPI_LIBUSB OFF CACHE BOOL", cmake)

    def test_release_setup_uses_pinned_git_and_normalizes_command_path(self):
        common = (ROOT / "tools/release-common.ps1").read_text(encoding="utf-8")
        provision = (ROOT / "tools/provision-toolchain.ps1").read_text(
            encoding="utf-8"
        )

        get_git = common.split("function Get-PinyonGit", 1)[1]
        self.assertNotIn("Get-Command git.exe", get_git)
        self.assertIn("$config.git.install_path", get_git)
        self.assertNotIn("Get-Command git.exe", provision)
        self.assertIn("$config.git.install_path", provision)
        self.assertIn("ConvertTo-PinyonCommandPath", common)
        self.assertIn("$inheritedPath = $env:PATH", common)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_command_path_removes_entry_quotes_without_losing_parentheses(self):
        command = (
            ". ./tools/release-common.ps1; "
            "[Console]::Out.Write((ConvertTo-PinyonCommandPath "
            "-PathValue $env:PINYON_TEST_PATH))"
        )
        environment = os.environ.copy()
        environment["PINYON_TEST_PATH"] = (
            'C:\\Windows;"C:\\Program Files (x86)\\Steam\\ext\\bin";'
            "C:\\Tools"
        )
        completed = subprocess.run(
            ["powershell", "-NoLogo", "-NoProfile", "-Command", command],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "C:\\Windows;C:\\Program Files (x86)\\Steam\\ext\\bin;C:\\Tools",
        )

    def test_launcher_payload_has_every_required_script(self):
        required = {
            "build-preview.ps1", "create-crash-report.ps1", "install-build-tools.ps1", "launch-preview.ps1",
            "prepare-rexglue.ps1", "provision-toolchain.ps1", "release-common.ps1",
            "set-graphics-experiment.ps1", "setup-preview.ps1", "verify-codegen-log.ps1",
            "verify-game.ps1",
        }
        self.assertTrue(required.issubset({p.name for p in (ROOT / "tools").glob("*.ps1")}))
        package_script = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        for shipped in ("set-graphics-experiment.ps1", "verify-codegen-log.ps1"):
            self.assertIn(shipped, package_script)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_packaged_source_provenance_does_not_require_a_git_worktree(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-provenance-") as temporary:
            root = pathlib.Path(temporary)
            (root / "config").mkdir()
            commit = "a" * 40
            (root / "config/source-provenance.json").write_text(
                json.dumps({"schema_version": 1, "commit": commit, "dirty": False}),
                encoding="utf-8",
            )
            command = (
                f". '{ROOT / 'tools/release-common.ps1'}'; "
                f"$result = Get-PinyonSourceProvenance -Root '{root}' "
                "-Git 'Z:\\missing\\git.exe'; "
                "[Console]::Out.Write($result.Commit + '|' + $result.Dirty)"
            )
            completed = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-Command", command],
                capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, commit + "|False")

    def test_graphics_schema_and_diagnostics_contract(self):
        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        self.assertIn("constexpr uint32_t kConfigSchema = 10", app)
        self.assertIn(".schema", app)
        for setting in ("anisotropic_override", "swap_post_effect", "draw_resolution_scale_x"):
            self.assertIn(setting, app)
            self.assertIn(setting, (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        for setting in ("host_present_fps_limit", "host_present_sleep_spin"):
            self.assertIn(setting, app)
            self.assertIn(setting, (ROOT / "tools/set-graphics-experiment.ps1").read_text(encoding="utf-8"))
            self.assertIn(setting, (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        self.assertIn("xma_relaxed_padding_admission = false", app)
        self.assertIn("xma_no_space_stalls", (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        self.assertIn("zpd_stale_result_rejections", (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        zpd_patch = ROOT / "patches/rexglue/0039-gpu-zpd-report-lifecycle-d3d12.patch"
        self.assertTrue(zpd_patch.is_file())
        self.assertIn("ZPDLifecycle", zpd_patch.read_text(encoding="utf-8"))
        policy_patch = ROOT / "patches/rexglue/0040-fh1-zpd-end-policy-and-telemetry.patch"
        self.assertTrue(policy_patch.is_file())
        self.assertIn("ZPDClassification", policy_patch.read_text(encoding="utf-8"))
        resolve_patch = ROOT / "patches/rexglue/0041-fh1-resolve-readback-counters.patch"
        self.assertTrue(resolve_patch.is_file())
        resolve_text = resolve_patch.read_text(encoding="utf-8")
        for counter in ("resolve_readback_requests", "resolve_readback_bytes",
                        "resolve_readback_full_waits", "resolve_readback_wait_time_ns"):
            self.assertIn(counter, resolve_text)

    def test_partial_vector_store_qualification_contract(self):
        patch = ROOT / "patches/rexglue/0042-ppc-partial-vector-store-regression-tests.patch"
        self.assertTrue(patch.is_file())
        patch_text = patch.read_text(encoding="utf-8")
        for marker in ("test_stvlx_offset_0", "test_stvlx_offset_15",
                       "test_stvrx_offset_0", "test_stvrx_offset_15",
                       "test_stvlx_memcpy_head", "test_stvrx_memcpy_tail",
                       "randomized_differential", "0x5EED07A1"):
            self.assertIn(marker, patch_text)
        qualifier = (ROOT / "tools/qualify-partial-vector-store.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("pinyon-shift.partial-vector-store-qualification.v1", qualifier)
        self.assertIn("ordered_patches", qualifier)
        self.assertIn("generated_functions_sha256", qualifier)

    def test_renderer_and_stub_instrumentation_is_bounded(self):
        stub_patch = (ROOT / "patches/rexglue/0031-sdk-stub-reachability-summary.patch").read_text(encoding="utf-8")
        self.assertIn("kMaximumStubReachabilityEntries = 128", stub_patch)
        self.assertIn("SDK_STUB first module={}", stub_patch)
        self.assertIn("SDK_STUB summary", stub_patch)
        memexport_patch = (ROOT / "patches/rexglue/0032-memexport-coherency-counters.patch").read_text(encoding="utf-8")
        for counter in ("memexport_draws", "memexport_bytes", "memexport_sync_fallbacks",
                        "memexport_queue_waits", "memexport_fence_waits"):
            self.assertIn(counter, memexport_patch)

    def test_runtime_config_migrates_vehicle_stabilization_and_menu_accept_input(self):
        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        hooks = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        launcher_xaml = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("constexpr uint32_t kConfigSchema = 10;", app)
        self.assertRegex(app, r"pinyon_shift_config_schema,\s*10,")
        self.assertIn('"pinyon_shift_stabilize_vehicle_presentation = false\\n"', app)
        self.assertIn('"keybind_a = \\"LMB,Space\\"\\n"', app)
        self.assertIn("schema < 1 || schema > 9", app)
        self.assertIn('"occlusion_query = \\"legacy\\"\\n"', app)
        self.assertIn('"zpd_end_policy = \\"report_layout\\"\\n"', app)
        self.assertIn('"readback_resolve = \\"none\\"\\n"', app)
        self.assertIn('"clear_memory_page_state = true\\n"', app)
        self.assertIn("Accurate showroom", launcher_xaml)
        self.assertIn("DisableMotionBlurCheckBox", launcher_xaml)
        self.assertIn("DisableDepthOfFieldCheckBox", launcher_xaml)
        self.assertIn("NativeRendererComboBox", launcher_xaml)
        self.assertIn("ResetRendererButton", launcher_xaml)
        self.assertIn('Environment.GetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT")', launcher)
        self.assertIn('"-StateRoot", _stateRoot', launcher)
        self.assertIn("DetectPendingReport();\n            UpdatePrimaryButton();", launcher)
        self.assertIn("Controller A, Space, or left click.", launcher)
        self.assertRegex(
            hooks,
            r"pinyon_shift_stabilize_vehicle_presentation,\s*false,",
        )

    def test_exact_hash_post_processing_substitutions_are_shipped(self):
        patch = (ROOT / "config/rexglue/analysis/fh1-post-processing.toml").read_text(
            encoding="utf-8"
        )
        for address in ("0x82D7894C", "0x8245B494", "0x8245846C", "0x8245849C"):
            self.assertIn(address, patch)
        self.assertIn("DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C", patch)
        build = (ROOT / "tools/build-preview.ps1").read_text(encoding="utf-8")
        self.assertIn("guest_codegen_patch_set_sha256", build)
        self.assertIn("does not match the exact supported EPIC-08 patch target", build)

    def test_8bitdo_ultimate_2c_wired_mapping_is_shipped(self):
        mappings = (ROOT / "config/gamecontrollerdb.txt").read_text(encoding="utf-8")
        matching = [
            line for line in mappings.splitlines()
            if line and not line.startswith("#") and "c82d00001d300000" in line.lower()
        ]
        self.assertEqual(len(matching), 2)
        for line in matching:
            for binding in (
                "a:b0", "b:b1", "lefttrigger:a3", "righttrigger:a4",
                "leftx:a0", "lefty:a1", "rightx:a2", "righty:a5",
                "start:b11", "platform:Windows",
            ):
                self.assertIn(binding, line)

        package_script = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("config/gamecontrollerdb.txt", package_script)

        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn(".pinyon-source-sha256", launcher)
        self.assertIn("StageControllerMappings", launcher)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_crash_report_redacts_paths_and_excludes_sensitive_files(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-report-") as temporary:
            root = pathlib.Path(temporary)
            state = root / "state"
            executable = root / "pinyon_shift.exe"
            executable.write_bytes(b"public-test-executable")
            (state / "logs").mkdir(parents=True)
            (state / "crashes").mkdir(parents=True)
            private_path = str(root / "private" / getpass.getuser())
            (state / "logs" / "runtime.log").write_text(
                f"game path: {private_path}\nlast useful line\n", encoding="utf-8"
            )
            (state / "logs" / "session.jsonl").write_text(
                json.dumps({"event": "process.start", "path": private_path}) + "\n",
                encoding="utf-8",
            )
            (state / "logs" / "session.perf.csv").write_text(
                "frame_time_us,xma_no_space_stalls,xma_no_progress_stalls,xma_stall_recoveries\n"
                "10000,2,1,0\n20000,3,0,1\n",
                encoding="utf-8",
            )
            crash = state / "crashes" / "test-unhandled.txt"
            crash.write_text(
                "Pinyon Shift unhandled exception\n"
                "code=0xC0000005 address=0000000012345678 thread=7\n"
                "session=test\n"
                "fault_module=pinyon_shift.exe fault_offset=0x1234\n"
                "#0 0x0000000012345678 TestFunction+0x4\n"
                f"source={private_path}\n",
                encoding="utf-8",
            )
            (state / "crashes" / "test-unhandled.dmp").write_bytes(b"private-memory")

            completed = subprocess.run(
                [
                    "powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ROOT / "tools/create-crash-report.ps1"),
                    "-StateRoot", str(state), "-Executable", str(executable),
                    "-StartedUtc", "2000-01-01T00:00:00Z", "-ProcessId", "7",
                    "-ExitCode", "-1073741819", "-Json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            with zipfile.ZipFile(result["bundle"]) as archive:
                names = set(archive.namelist())
                self.assertIn("report.json", names)
                self.assertIn("crash.txt", names)
                self.assertFalse(any(name.lower().endswith(".dmp") for name in names))
                combined = "\n".join(
                    archive.read(name).decode("utf-8") for name in names
                )
            self.assertNotIn(str(root), combined)
            self.assertNotIn(getpass.getuser().lower(), combined.lower())
            self.assertTrue("<USER_PROFILE>" in combined or "<USERNAME>" in combined)
            with zipfile.ZipFile(result["bundle"]) as archive:
                manifest = json.loads(archive.read("report.json"))
            self.assertFalse(manifest["privacy"]["memory_dump_included"])
            self.assertFalse(manifest["privacy"]["audio_payload_included"])
            self.assertTrue(manifest["audio"]["xma_stalls"]["available"])
            self.assertEqual(manifest["audio"]["xma_stalls"]["no_space"], 5)
            self.assertEqual(manifest["audio"]["xma_stalls"]["no_progress"], 1)
            self.assertEqual(manifest["audio"]["xma_stalls"]["recoveries"], 1)
            self.assertEqual(manifest["exception"]["fault_offset"], "0x1234")


if __name__ == "__main__":
    unittest.main()
