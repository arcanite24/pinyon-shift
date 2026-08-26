import getpass
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ReleaseContractTests(unittest.TestCase):
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
        self.assertEqual(len(patches), 30)
        self.assertEqual(
            patches[-1].name,
            "0030-v0.10-deduplicate-resume-alias-registrations.patch",
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
        self.assertIn("function New-DeterministicZip", package_script)
        self.assertIn("FromUnixTimeSeconds", package_script)

    def test_launcher_payload_has_every_required_script(self):
        required = {
            "build-preview.ps1", "create-crash-report.ps1", "install-build-tools.ps1", "launch-preview.ps1",
            "prepare-rexglue.ps1", "provision-toolchain.ps1", "release-common.ps1",
            "setup-preview.ps1", "verify-game.ps1",
        }
        self.assertTrue(required.issubset({p.name for p in (ROOT / "tools").glob("*.ps1")}))

    def test_vehicle_presentation_stabilization_is_migrated_to_opt_in(self):
        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        hooks = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        self.assertIn("constexpr uint32_t kConfigSchema = 2;", app)
        self.assertRegex(app, r"pinyon_shift_config_schema,\s*2,")
        self.assertIn('"pinyon_shift_stabilize_vehicle_presentation = false\\n"', app)
        self.assertRegex(
            hooks,
            r"pinyon_shift_stabilize_vehicle_presentation,\s*false,",
        )

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
            self.assertEqual(manifest["exception"]["fault_offset"], "0x1234")


if __name__ == "__main__":
    unittest.main()
