import getpass
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ReleaseContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_visual_studio_selection_excludes_incompatible_standard_library(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-vswhere-") as directory:
            root = pathlib.Path(directory)
            executable = root / "Microsoft Visual Studio/Installer/vswhere.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            environment = os.environ.copy()
            environment["PINYON_TEST_ROOT"] = str(root)
            command = r"""
. ./tools/release-common.ps1
${env:ProgramFiles(x86)} = $env:PINYON_TEST_ROOT
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
Set-Item -Path "Function:$vswhere" -Value {
    param([Parameter(ValueFromRemainingArguments=$true)] $Arguments)
    $rangeIndex = [Array]::IndexOf($Arguments, '-version')
    if ($rangeIndex -lt 0) { return 'incompatible-vs2019' }
    if ($Arguments[$rangeIndex + 1] -ne '[17.1,)') { throw 'Unexpected supported version range' }
    if ($env:PINYON_TEST_HAS_SUPPORTED -eq '1') { return 'compatible-vs2022' }
}
$env:PINYON_TEST_HAS_SUPPORTED = '0'
if ($null -ne (Get-PinyonVisualStudioRoot -AllowMissing)) { throw 'Old tools bypass provisioning' }
try {
    Get-PinyonVisualStudioRoot | Out-Null
    throw 'Missing tools were accepted'
} catch {
    if ($_.Exception.Message -notmatch 'provision-toolchain.ps1') { throw }
}
$env:PINYON_TEST_HAS_SUPPORTED = '1'
if ((Get-PinyonVisualStudioRoot) -ne 'compatible-vs2022') { throw 'Supported tools were not selected' }
"""
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_vsdevcmd_uses_safe_temp_and_restores_portable_install_paths(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-vs-temp-") as directory:
            root = pathlib.Path(directory)
            batch = root / "Build Tools/Common7/Tools/VsDevCmd.bat"
            batch.parent.mkdir(parents=True)
            batch.write_text(
                '@echo off\n'
                'if "1" == "0" (\n'
                '  echo %TEMP%\\dd_vsdevcmd17_preinit_env.log\n'
                ')\n'
                'if "%PINYON_TEST_VS_FAIL%" == "1" exit /b 17\n'
                'set "PINYON_TEST_VS_TEMP=%TEMP%"\n'
                'exit /b 0\n')
            environment = os.environ.copy()
            environment["PINYON_TEST_VS_ROOT"] = str(root / "Build Tools")
            environment["PINYON_TEST_INSTALL"] = str(root / "Forza (Pinyon Shift)")
            command = r"""
. ./tools/release-common.ps1
$ErrorActionPreference = 'Stop'
function Get-PinyonVisualStudioRoot { $env:PINYON_TEST_VS_ROOT }
function Get-PinyonCMake { 'test-cmake' }
function Assert-PinyonBuildCapabilities { }
$env:TEMP = Join-Path $env:PINYON_TEST_INSTALL 'data\temp'
$env:TMP = Join-Path $env:PINYON_TEST_INSTALL 'other (temp)'
$expectedTemp = $env:TEMP
$expectedTmp = $env:TMP
$env:PINYON_TEST_VS_FAIL = '0'
Enter-PinyonBuildEnvironment | Out-Null
if ($env:PINYON_TEST_VS_TEMP -match '[ ()]') { throw 'Unsafe child TEMP' }
if ($env:TEMP -ne $expectedTemp -or $env:TMP -ne $expectedTmp) { throw 'Temp paths changed on success' }
$env:PINYON_TEST_VS_FAIL = '1'
try {
    Enter-PinyonBuildEnvironment | Out-Null
    throw 'Failed tools were accepted'
} catch {
    if ($_.Exception.Data['exit_code'] -ne 17) { throw }
}
if ($env:TEMP -ne $expectedTemp -or $env:TMP -ne $expectedTmp) { throw 'Temp paths changed on failure' }
exit 0
"""
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_workflow_publishes_only_preview_channels_as_prereleases(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("$release.channel -eq 'preview'", workflow)
        self.assertIn("$release.channel -ne 'stable'", workflow)
        self.assertIn("$arguments += '--prerelease'", workflow)
        self.assertIn('docs/releases/$($release.version).md', workflow)
        self.assertIn("@('--notes-file', $notesPath, '--title', $title)", workflow)
        self.assertNotIn(
            "--generate-notes --prerelease --verify-tag",
            workflow,
        )

    def test_preview_release_uses_dev_and_stable_keeps_main(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("if ($release.channel -eq 'preview') { 'dev' } else { 'main' }", workflow)
        self.assertIn('--main-ref "refs/remotes/origin/$branch"', workflow)


    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_build_command_keeps_stderr_and_exit_status(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-build-log-") as directory:
            environment = os.environ.copy()
            environment["PINYON_TEST_DIR"] = directory
            command = r"""
. ./tools/release-common.ps1
$ErrorActionPreference = 'Stop'
foreach ($code in @(0, 7)) {
    $log = Join-Path $env:PINYON_TEST_DIR "$code.log"
    try {
        Invoke-PinyonBuildCommand $env:ComSpec @('/d', '/c', "echo diagnostic 1>&2 & echo output & exit /b $code") $log 'build failed' | Out-Host
        if ($code -ne 0) { throw 'Failure was swallowed' }
    } catch {
        if ($code -eq 0 -or $_.Exception.Data['exit_code'] -ne $code -or $_.Exception.Data['build_log'] -ne $log) { throw }
    }
    $text = Get-Content -LiteralPath $log -Raw
    if ($text -notmatch 'diagnostic' -or $text -notmatch 'output') { throw 'Output missing' }
}
"""
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_cmake_rejects_old_version_and_prefers_local_install(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-cmake-") as directory:
            root = pathlib.Path(directory)
            (root / "config").mkdir()
            config = json.loads((ROOT / "config/release-toolchain.json").read_text())
            config["cmake"]["executable"] = "bin/cmake.cmd"
            (root / "config/release-toolchain.json").write_text(json.dumps(config))
            cmake = root / config["cmake"]["install_path"] / "bin/cmake.cmd"
            cmake.parent.mkdir(parents=True)
            environment = os.environ.copy()
            environment["PINYON_TEST_ROOT"] = str(root)
            command = r"""
. ./tools/release-common.ps1
function Get-PinyonRepoRoot { $env:PINYON_TEST_ROOT }
try { [Console]::Out.Write((Get-PinyonCMake -VisualStudioRoot $env:PINYON_TEST_ROOT)) }
catch { [Console]::Error.Write($_.Exception.Message); exit 2 }
"""
            for version, expected in (("3.20.0", 2), ("3.31.10", 0)):
                cmake.write_text(f"@echo cmake version {version}\n@exit /b 0\n")
                result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                        cwd=ROOT, env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected == 0:
                    self.assertTrue(pathlib.Path(result.stdout).samefile(cmake))
                else:
                    self.assertIn("provision-toolchain.ps1", result.stderr)

    def test_packaged_sources_cover_literal_cmake_inputs(self):
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        include = package.split("$include = @(", 1)[1].split("\n)", 1)[0]
        paths = re.findall(r"'([^']+)'", include)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        sources = re.findall(r"^\s*((?:src|tests|tools|mods_src)/[^\s)]+)", cmake, re.MULTILINE)
        # Include directories the build needs.
        sources += ["include/pinyon_mod.h"]
        # Scripts the packaged launcher runs.
        launch = (ROOT / "tools/launch-preview.ps1").read_text(encoding="utf-8")
        sources += ["tools/" + name for name in
                    re.findall(r"Join-Path \$PSScriptRoot '([^'.][^']*)'", launch)]
        self.assertTrue(sources)
        for source in sources:
            self.assertTrue((ROOT / source).is_file(), source)
            self.assertTrue(any(source == path or source.startswith(path + "/")
                                for path in paths), source)

    def test_supported_dump_uses_exact_hash_and_size(self):
        data = json.loads((ROOT / "config/supported-dumps.json").read_text())
        self.assertEqual(data["policy"]["match"], "exact_sha256_and_size")
        self.assertEqual(data["policy"]["unknown_dump_action"], "reject")
        for dump in data["dumps"]:
            self.assertGreater(dump["iso"]["size_bytes"], 0)
            self.assertRegex(dump["iso"]["sha256"], r"^[0-9A-F]{64}$")

    def test_downloads_are_https_and_sha256_pinned(self):
        data = json.loads((ROOT / "config/release-toolchain.json").read_text())
        for key in ("git", "xz", "llvm", "extract_xiso", "python", "cmake"):
            item = data[key]
            self.assertTrue(item["url"].startswith("https://"))
            self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$")
        self.assertTrue(data["visual_studio"]["bootstrap_url"].startswith("https://"))
        rexglue = data["rexglue"]
        self.assertEqual(rexglue["repository"], "https://github.com/arcanite24/shiftglue-sdk")
        self.assertRegex(rexglue["revision"], r"^[0-9a-f]{40}$")

    def test_shiftglue_submodule_matches_the_release_pin(self):
        toolchain = json.loads((ROOT / "config/release-toolchain.json").read_text())
        rexglue = toolchain["rexglue"]
        modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
        preset = (ROOT / "CMakePresets.json").read_text(encoding="utf-8")
        prepare = (ROOT / "tools/prepare-rexglue.ps1").read_text(encoding="utf-8")
        self.assertIn(rexglue["repository"], modules)
        self.assertIn(rexglue["submodule_path"], modules)
        self.assertIn(rexglue["submodule_path"], preset)
        self.assertIn("Resolve-PinyonRexGlueRoot", prepare)
        self.assertNotIn("patch_directory", json.dumps(toolchain))
        self.assertFalse(any((ROOT / "patches/rexglue").glob("*.patch")))


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
        self.assertIn("$<TARGET_FILE:rexruntime>", integration)
        self.assertIn("$<TARGET_FILE:rexgpu-fh1>", integration)
        self.assertIn("DEPENDS ${target_name} rexruntime rexgpu-fh1", integration)
        graphics_cmake = (
            ROOT / "thirdparty/shiftglue-sdk/src/graphics/CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("rexgpu-fh1-producer SHARED EXCLUDE_FROM_ALL", graphics_cmake)
        self.assertIn("REXGPU_FH1_SHADER_PRODUCER=1", graphics_cmake)
        self.assertNotIn("rexgpu-fh1-producer", integration)
        self.assertNotIn("packet_disassembler.cpp", graphics_cmake)
        command_processor = (
            ROOT / "thirdparty/shiftglue-sdk/src/graphics/d3d12/command_processor.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("isolated_draw_request_observer", command_processor)
        self.assertNotIn("IsolatedReplay", command_processor)
        # The D3D12 plugin no longer has a Xenos render target cache.
        self.assertFalse(
            (
                ROOT / "thirdparty/shiftglue-sdk/src/graphics/d3d12/render_target_cache.cpp"
            ).exists()
        )
        self.assertNotIn("d3d12/render_target_cache.cpp", graphics_cmake)
        launcher = (ROOT / "tools/launch-preview.ps1").read_text(encoding="utf-8")
        # The producer carries the build type's plugin postfix (rd, d or none).
        self.assertIn('"rexgpu-fh1-producer$pluginPostfix.dll"', launcher)
        self.assertIn("Remove-Item -LiteralPath $stagedShaderProducer", launcher)

        package_script = (ROOT / "tools/package-launcher.ps1").read_text()
        self.assertIn("$_.Name -ne 'generated'", package_script)
        self.assertIn("Add-Type -AssemblyName System.IO.Compression\n", package_script)
        self.assertIn("function New-DeterministicZip", package_script)
        self.assertIn("FromUnixTimeSeconds", package_script)

    def test_launch_preview_forwards_arguments_and_stages_prepared_shaders(self):
        launch = (ROOT / "tools/launch-preview.ps1").read_text(encoding="utf-8")
        self.assertIn("[string[]]$GameArguments = @()", launch)
        self.assertIn("$normalizedGameArguments = @($GameArguments)", launch)
        self.assertIn("$start.ArgumentList = $normalizedGameArguments", launch)
        self.assertNotIn("pinyon_shift_fh1_require_precompiled_shaders", launch)
        self.assertIn("prepare-fh1-shaders.ps1", launch)
        self.assertNotIn("fh1-native-prewarm/cache", launch)
        self.assertIn("native_pipeline_cache = $stagedNativePipelineCache", launch)

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

    def test_powershell_is_started_by_full_path(self):
        # A PATH without the WindowsPowerShell folder failed setup with "The
        # specified file cannot be found" (#317).
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        provision = (ROOT / "tools/provision-toolchain.ps1").read_text(encoding="utf-8")

        self.assertNotIn('FileName = "powershell.exe"', launcher)
        self.assertIn('"WindowsPowerShell", "v1.0", "powershell.exe"', launcher)
        self.assertNotIn("'powershell.exe'", provision)
        self.assertIn("(Get-Process -Id $PID).Path", provision)

    @unittest.skipUnless((ROOT / ".git").exists(), "needs the repository's git metadata")
    def test_release_sdk_revision_matches_the_submodule(self):
        # A packaged install fetches this revision instead of the submodule, so
        # an SDK bump that missed it built releases against an older SDK.
        toolchain = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
        tree = subprocess.run(
            ["git", "ls-tree", "HEAD", toolchain["rexglue"]["submodule_path"]],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()

        self.assertEqual(tree[1], "commit")
        self.assertEqual(toolchain["rexglue"]["revision"], tree[2])

    def test_llvm_is_extracted_with_windows_tar(self):
        # GNU tar from Git's Unix tools reads "E:\..." as a remote host.
        common = (ROOT / "tools/release-common.ps1").read_text(encoding="utf-8")

        self.assertIn("Join-Path ([Environment]::SystemDirectory) 'tar.exe'", common)
        self.assertNotIn("& tar.exe", common)

    def test_declined_build_tools_permission_is_explained(self):
        # A declined UAC prompt surfaced only as a localized "the operation was
        # canceled by the user" (#318).
        provision = (ROOT / "tools/provision-toolchain.ps1").read_text(encoding="utf-8")

        self.assertIn("NativeErrorCode -eq 1223", provision)
        self.assertIn("administrator permission was declined", provision)

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
            "host-config.ps1", "set-graphics-experiment.ps1", "setup-preview.ps1",
            "verify-codegen-log.ps1", "verify-game.ps1",
        }
        self.assertTrue(required.issubset({p.name for p in (ROOT / "tools").glob("*.ps1")}))
        package_script = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        for shipped in ("host-config.ps1", "set-graphics-experiment.ps1", "verify-codegen-log.ps1"):
            self.assertIn(shipped, package_script)

    def test_launcher_payload_ships_the_android_build(self):
        # The launcher's Build Android APK action runs build-android.ps1, which
        # runs pinyon.py; pinyon.py imports pinyon_android, which reads the
        # toolchain pins and packages the android/ sources.
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        include = package.split("$include = @(", 1)[1].split("\n)", 1)[0]
        paths = set(re.findall(r"'([^']+)'", include))
        for required in ("tools/pinyon.py", "tools/pinyon_android.py", "tools/build-android.ps1",
                         "config/android-toolchain.json", "android"):
            self.assertIn(required, paths)
            self.assertTrue((ROOT / required).exists(), required)
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8")
        self.assertIn('"build-android.ps1"', launcher)
        self.assertIn("-AcceptAndroidLicenses", launcher)
        # The bootstrap downloads are pinned like the PC toolchain's.
        android = json.loads((ROOT / "config/android-toolchain.json").read_text(encoding="utf-8"))
        for pin in (android["bootstrap"]["cmdline_tools"], android["bootstrap"]["jdk"]):
            self.assertTrue(pin["url"].startswith("https://"))
            self.assertRegex(pin["sha256"], r"^[0-9A-F]{64}$")

    def test_native_tools_use_the_configured_sdk_and_ship_their_sources(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        package = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        self.assertNotIn("thirdparty/shiftglue-sdk/", cmake)
        self.assertIn("${REXSDK_DIR}/src/graphics/fh1_shader_pack.cpp", cmake)
        for source in ("tests/native_renderer", "tools/fh1_archive_extract.cpp",
                       "tools/fh1_texture_import.cpp", "tools/thread_sampler.cpp",
                       "tools/extract-fh1-shader-corpus.py",
                       "tools/build-fh1-gpu-prewarm.py", "tools/produce-fh1-artifacts.ps1",
                       "config/render-tests"):
            self.assertIn("'" + source + "'", package)
            self.assertTrue((ROOT / source).exists())

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_python_resolver_uses_local_runtime_without_path_fallback(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-python-") as directory:
            root = pathlib.Path(directory)
            (root / "config").mkdir()
            shutil.copyfile(ROOT / "config/release-toolchain.json", root / "config/release-toolchain.json")
            config = json.loads((root / "config/release-toolchain.json").read_text())["python"]
            executable = root / config["install_path"] / config["executable"]
            environment = os.environ.copy()
            environment["PINYON_TEST_ROOT"] = str(root)
            environment["PATH"] = ""
            command = (
                ". ./tools/release-common.ps1; "
                "function Get-PinyonRepoRoot { $env:PINYON_TEST_ROOT }; "
                "try { [Console]::Out.Write((Get-PinyonPython)) } catch { exit 2 }"
            )
            args = [shutil.which("powershell"), "-NoLogo", "-NoProfile", "-Command", command]
            missing = subprocess.run(args, cwd=ROOT, env=environment, capture_output=True)
            self.assertEqual(missing.returncode, 2)
            executable.parent.mkdir(parents=True)
            executable.touch()
            found = subprocess.run(args, cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(found.returncode, 0, found.stderr)
            self.assertTrue(pathlib.Path(found.stdout).samefile(executable))

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
    def test_artifact_production_preserves_existing_work_and_rejects_external_paths(self):
        local = ROOT / ".local"
        local.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pinyon-producer-test-", dir=local) as directory:
            work = pathlib.Path(directory)
            self.assertTrue(work.resolve().is_relative_to(local.resolve()))
            marker = work / "preserve.txt"
            marker.write_text("previous production", encoding="utf-8")
            for path, error in ((str(work.relative_to(ROOT)), "existing production is never overwritten"),
                                ("../outside-production", "outside")):
                result = subprocess.run(
                    ["powershell", "-NoLogo", "-NoProfile", "-File",
                     str(ROOT / "tools/produce-fh1-artifacts.ps1"), "-WorkRoot", path,
                     "-RenderTestScript", "not-needed.fh1test"], cwd=ROOT,
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertEqual(marker.read_text(encoding="utf-8"), "previous production")

    def test_launcher_persists_setup_output_in_the_setup_log_directory(self):
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn('Path.Combine(logs, "launcher.log")', launcher)
        self.assertIn('Path.Combine(_repositoryRoot, ".local", "logs")', launcher)
        self.assertNotIn('var logs = Path.Combine(_stateRoot, "logs")', launcher)

    def test_setup_rejects_a_running_preview_before_building(self):
        setup = (ROOT / "tools/setup-preview.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-Process -Name 'pinyon_shift'", setup)
        self.assertIn("Close every running Pinyon Shift preview", setup)

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
        self.assertIn("constexpr uint32_t kConfigSchema = 27", app)
        self.assertIn(".schema", app)
        for setting in ("anisotropic_override", "swap_post_effect", "draw_resolution_scale_x"):
            self.assertIn(setting, app)
            self.assertIn(setting, (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        for setting in ("host_present_fps_limit", "host_present_sleep_spin",
                        "pinyon_shift_fh1_render_fps_limit"):
            self.assertIn(setting, app)
            self.assertIn(setting, (ROOT / "tools/set-graphics-experiment.ps1").read_text(encoding="utf-8"))
            self.assertIn(setting, (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8"))
        # The native renderer is the only renderer: crash reports carry it as
        # a constant rather than reading a retired renderer choice.
        crash_report = (ROOT / "tools/create-crash-report.ps1").read_text(encoding="utf-8")
        self.assertIn("renderer = 'native'", crash_report)
        for retired in ("fh1_renderer", "pinyon_shift_native_renderer", "xenos_authority",
                        "'xenos'"):
            self.assertNotIn(retired, crash_report)
        sdk = ROOT / "thirdparty/shiftglue-sdk"
        # One occlusion-query path: the modern ZPD lifecycle and classifier are gone.
        for retired in ("zpd_lifecycle.h", "zpd_policy.h", "zpd_report.h"):
            self.assertFalse((sdk / "include/rex/graphics" / retired).exists())
        counters = (sdk / "src/core/perf/counter.cpp").read_text()
        for counter in ("resolve_readback_requests", "resolve_readback_bytes",
                        "resolve_readback_full_waits", "resolve_readback_wait_time_ns"):
            self.assertIn(counter, counters)

    def test_partial_vector_store_qualification_contract(self):
        sdk = ROOT / "thirdparty/shiftglue-sdk"
        source = (sdk / "tests/ppc/asm/instr_partial_vector_store.s").read_text()
        source += (sdk / "resources/templates/test/ppc_test_cases_cpp.inja").read_text()
        for marker in ("test_stvlx_offset_0", "test_stvlx_offset_15",
                       "test_stvrx_offset_0", "test_stvrx_offset_15",
                       "test_stvlx_memcpy_head", "test_stvrx_memcpy_tail",
                       "randomized_differential", "0x5EED07A1"):
            self.assertIn(marker, source)
        qualifier = (ROOT / "tools/qualify-partial-vector-store.ps1").read_text()
        self.assertIn("pinyon-shift.partial-vector-store-qualification.v2", qualifier)
        self.assertIn("rexglue_dirty", qualifier)

    def test_renderer_and_stub_instrumentation_is_bounded(self):
        sdk = ROOT / "thirdparty/shiftglue-sdk"
        hook = (sdk / "include/rex/hook.h").read_text(encoding="utf-8")
        self.assertIn("kMaximumStubReachabilityEntries = 128", hook)
        self.assertIn("SDK_STUB summary", hook)
        counters = (sdk / "src/core/perf/counter.cpp").read_text(encoding="utf-8")
        for counter in ("memexport_draws", "memexport_bytes", "memexport_sync_fallbacks",
                        "memexport_queue_waits", "memexport_fence_waits"):
            self.assertIn(counter, counters)

    def test_runtime_config_migrates_vehicle_stabilization_and_menu_accept_input(self):
        sdk = ROOT / "thirdparty/shiftglue-sdk"
        app = (ROOT / "src/pinyon_shift_app.cpp").read_text(encoding="utf-8")
        hooks = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(
            encoding="utf-8"
        )
        launcher_xaml = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("constexpr uint32_t kConfigSchema = 27;", app)
        self.assertRegex(app, r"pinyon_shift_config_schema,\s*27,")
        self.assertIn('"pinyon_shift_stabilize_vehicle_presentation = false\\n"', app)
        self.assertIn('"keybind_a = \\"LMB,Space\\"\\n"', app)
        # Schemas 1..24 migrate; the current schema is accepted unchanged.
        self.assertIn("schema < 1 || schema >= kConfigSchema", app)
        self.assertNotIn('"fh1_renderer = \\"native\\"\\n"', app)
        self.assertNotIn('\\"xenos\\"', app)
        retired_block = app[app.index("for (const char* retired_setting : {"):]
        retired_block = retired_block[:retired_block.index("})")]
        for retired in (
            "fh1_renderer", "fh1_native_shadow", "fh1_native_shadow_dump_dir",
            "fh1_native_shadow_dump_frames", "fh1_native_shadow_verify",
            "fh1_native_shadow_verify_draws", "fh1_discovery_sampling",
            "fh1_owned_depth_clear", "fh1_owned_depth_tile_clear",
            "fh1_native_reflection_mips", "fh1_mip_decode_probe",
            "fh1_native_ui_boundary_probe", "fh1_glow_probe",
            "fh1_recycle_geometry_buffers", "fh1_contain_geometry_windows",
            "fh1_cache_geometry_rejections", "fh1_geometry_cache_mb",
            "native_stencil_value_output", "native_stencil_value_output_d3d12_intel",
            "pinyon_shift_native_race", "pinyon_shift_native_ui_live",
            "pinyon_shift_native_ordered_live_probe",
            "pinyon_shift_fh1_clear_producer_trace", "pinyon_shift_fh1_scene_dump",
            "pinyon_shift_snr04_live_worker",
        ):
            self.assertIn(f'"{retired}"', retired_block)
        graphics_tool = (ROOT / "tools/set-graphics-experiment.ps1").read_text(encoding="utf-8")
        self.assertIn("pinyon_shift_config_schema = 27", graphics_tool)
        self.assertIn("-gt 27", graphics_tool)
        self.assertNotIn("-gt 23", graphics_tool)
        # Apply writes the current schema and so bypasses the game's
        # migration: it must drop every setting that migration retires.
        tool_retired = graphics_tool[graphics_tool.index("$retiredSettings = @("):]
        tool_retired = tool_retired[:tool_retired.index(")")]
        for retired in re.findall(r'"([a-z0-9_]+)"', retired_block):
            self.assertIn(f"'{retired}'", tool_retired)
        self.assertIn("display.refresh.detected", app)
        # The refresh query lives in the platform layer (NP-12.2).
        self.assertIn("platform::DisplayRefreshRate", app)
        platform = (ROOT / "src/platform/host_platform.cpp").read_text(encoding="utf-8")
        self.assertIn("EnumDisplaySettingsW", platform)
        graphics = (
            ROOT / "thirdparty/shiftglue-sdk/src/graphics/graphics_system.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("REXCVAR_GET(video_mode_refresh_rate)", graphics)
        self.assertNotIn("render_fps_limit ? double(render_fps_limit) * 2.0 : 1000.0", graphics)
        self.assertIn("pinyon_shift_native_renderer_texture_bridge", app)
        self.assertNotIn('"occlusion_query = \\"legacy\\"\\n"', app)
        self.assertNotIn('"zpd_end_policy = \\"report_layout\\"\\n"', app)
        self.assertNotIn('"readback_resolve = \\"none\\"\\n"', app)
        self.assertNotIn("REXCVAR_DEFINE_BOOL(pinyon_shift_fh1_native_v4", app)
        self.assertNotIn("pinyon_shift_fh1_require_precompiled_shaders", app)
        pipeline_cache = (sdk / "src/graphics/d3d12/pipeline_cache.cpp").read_text(
            encoding="utf-8"
        )
        command_processor = (sdk / "src/graphics/d3d12/command_processor.cpp").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Fh1NativeV4Enabled", pipeline_cache)
        self.assertNotIn("Fh1NativeV4Enabled", command_processor)
        # The hand-written FH1 shader families were removed with the Xenos
        # renderer; the pack's translated shaders are the only bytecode.
        self.assertNotIn("kFh1UseNativeWorldVertexShaders", pipeline_cache)
        self.assertNotIn("kFh1UseNativeDepthMeshVertexShaders", pipeline_cache)
        self.assertNotIn("state_desc.PS = {shaders::fh1_world_lit_ps", pipeline_cache)
        self.assertIn("native_guest_output_gpu_timing_active_ = true;", command_processor)
        self.assertIn("EndNativeGuestOutputGpuTimingFrame();", command_processor)
        self.assertNotIn("fh1_world_lit_native_draw", command_processor)
        self.assertNotIn("IsFh1WorldLitNativeActive", command_processor)
        # The GPU execution corpus recorded nothing once native became the
        # only renderer and was removed with its key ABI (NP-0.5).
        self.assertFalse((ROOT / "src/native_renderer/fh1_gpu_corpus.cpp").exists())
        self.assertNotIn("GraphicsFh1ExecutionKey", (
            sdk / "include/rex/system/interfaces/graphics.h"
        ).read_text(encoding="utf-8"))
        self.assertIn("kFh1GpuPassTimingCapacity = 512", (
            sdk / "include/rex/graphics/d3d12/command_processor.h"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("fh1_execution_allowlist_", (
            sdk / "include/rex/graphics/d3d12/pipeline_cache.h"
        ).read_text(encoding="utf-8"))
        generic_command_processor = (
            sdk / "src/graphics/command_processor.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "WriteRegisterRangeFromRing(reader, base_index, count);",
            generic_command_processor,
        )
        self.assertIn('"clear_memory_page_state = false\\n"', app)
        self.assertNotIn("Accurate showroom", launcher_xaml)
        # NP-1.7: the launcher keeps only the internal resolution; the rest
        # is set in game and a launcher save must not overwrite it.
        self.assertIn("ResolutionComboBox", launcher_xaml)
        self.assertNotIn("DisableMotionBlurCheckBox", launcher_xaml)
        self.assertNotIn("AnisotropyComboBox", launcher_xaml)
        self.assertNotIn('"-Anisotropy"', launcher)
        self.assertIn('"-ResolutionScale", SelectedTag(ResolutionComboBox)', launcher)
        # Schema 27: the graphics API (Vulkan by default) is chosen before start.
        self.assertIn('"-GraphicsApi", SelectedTag(GraphicsApiComboBox)', launcher)
        self.assertIn("GraphicsApiComboBox", launcher_xaml)
        # The output scaling, with the rendered and shown sizes beside it.
        self.assertIn('"-OutputScaling", SelectedTag(OutputScalingComboBox)', launcher)
        self.assertIn("ResolutionLineText", launcher_xaml)
        # The Treasure Map, on unless the player turns it off.
        self.assertIn('"-TreasureMap", TreasureMapCheckBox.IsChecked == true', launcher)
        self.assertIn('x:Name="TreasureMapCheckBox"', launcher_xaml)
        self.assertNotIn("NativeRendererComboBox", launcher_xaml)
        self.assertNotIn("ResetRendererButton", launcher_xaml)
        # The renderer choice is gone: native is the only renderer.
        self.assertNotIn("RENDERER", launcher_xaml)
        self.assertNotIn("RendererComboBox", launcher_xaml)
        self.assertNotIn("Xenos", launcher_xaml)
        self.assertNotIn("RendererComboBox", launcher)
        self.assertNotIn('"-Renderer"', launcher)
        self.assertNotIn('JsonPropertyName("renderer")', launcher)
        self.assertIn('Environment.GetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT")', launcher)
        self.assertIn('"-StateRoot", _stateRoot', launcher)
        self.assertIn("DetectPendingReport();\n            UpdatePrimaryButton();", launcher)
        self.assertIn("Controller A, Space, or left click.", launcher)
        self.assertRegex(
            hooks,
            r"pinyon_shift_stabilize_vehicle_presentation,\s*false,",
        )

    def test_tools_no_longer_select_a_renderer(self):
        # The native renderer is the only renderer; tools must not pass the
        # retired fh1_renderer cvar or offer a renderer choice.
        for name in ("replay-fh1-frame.py", "test-fh1-frame-replays.py"):
            source = (ROOT / "tools" / name).read_text(encoding="utf-8")
            self.assertNotIn("--renderer", source)
            self.assertNotIn("fh1_renderer", source)
            self.assertNotIn("xenos", source)
        discovery = (ROOT / "tools/start-fh1-discovery.ps1").read_text(encoding="utf-8")
        self.assertNotIn("fh1_discovery_sampling", discovery)
        self.assertNotIn("pinyon_shift_fh1_scene_dump", discovery)
        production = (ROOT / "tools/produce-fh1-artifacts.ps1").read_text(encoding="utf-8")
        self.assertNotIn("native_renderer.v4.execution.summary", production)
        self.assertIn("FH1 native executor enabled: native", production)

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
                f"[2099-01-01 00:00:00.000] game path: {private_path}\nlast useful line\n", encoding="utf-8"
            )
            (state / "logs" / "test.jsonl").write_text(
                json.dumps({"event": "process.start", "path": private_path, "pid": "7",
                            "utc": "2000-01-01T00:00:00Z", "session": "test"}) + "\n" +
                json.dumps({"event": "logging.ready", "pid": "7", "session": "test",
                            "renderer": "vulkan"}) + "\n",
                encoding="utf-8",
            )
            (state / "logs" / "test.perf.csv").write_text(
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
