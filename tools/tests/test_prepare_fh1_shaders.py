import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SDK = "thirdparty/shiftglue-sdk"
GRAPHICS_SOURCES = (
    *(f"{SDK}/include/rex/graphics/{name}.h" for name in (
        "fh1_shader_pack", "d3d12/host_render_config", "d3d12/pipeline_cache",
        "d3d12/primitive_processor", "d3d12/shader", "flags", "format/ucode",
        "primitive_processor", "registers", "util/draw", "xenos", "pipeline_util",
        "pipeline/render_target/psi_color_format", "pipeline/shader/dxbc_translator")),
    f"{SDK}/include/rex/graphics/register_table.inc",
    *(f"{SDK}/src/graphics/{name}.cpp" for name in (
        "fh1_shader_pack", "d3d12/host_render_config", "d3d12/pipeline_cache",
        "d3d12/primitive_processor", "d3d12/shader", "flags", "format/ucode",
        "primitive_processor", "registers", "util/draw", "xenos",
        "pipeline/shader/dxbc_translator", "pipeline/shader/spirv_translator")),
)


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
class ShaderPreparationTests(unittest.TestCase):
    def test_prepare_reuse_repair_invalidation_and_failed_retry(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-prepare-") as directory:
            root = pathlib.Path(directory)
            for path in (
                "out/build/win-amd64-release/pinyon_shift.exe",
                "out/build/win-amd64-release/rexgpu-fh1.dll",
                "out/build/win-amd64-release/rexruntime.dll",
                "config/supported-dumps.json",
                "config/render-tests/fh1-shader-preparation.fh1test",
                "tools/extract-fh1-shader-corpus.py", "tools/build-fh1-gpu-prewarm.py",
                "tools/fh1_archive_extract.cpp",
                "tools/native-shader-pack.py",
                "src/native_renderer/shader_capture.cpp",
                # A release install has no .git and no submodule: setup clones
                # the pinned SDK to .local/rexglue (issue #322).
                *(path.replace(SDK, ".local/rexglue", 1) for path in GRAPHICS_SOURCES),
            ):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("input")
            shutil.copyfile(ROOT / "config/release-toolchain.json", root / "config/release-toolchain.json")
            for name in ("prepare-fh1-shaders.ps1", "release-common.ps1"):
                shutil.copyfile(ROOT / "tools" / name, root / "tools" / name)
            (root / "tools/produce-fh1-artifacts.ps1").write_text(r'''
param($WorkRoot, $RenderTestScript, $GameRoot, $BuildDirectory, $RuntimeConfig, $Scale, $SeedShaderCacheRoot, $ShaderMissDir, [switch]$Hidden, [switch]$JsonEvents, [switch]$IncludeOpeningMovies, [switch]$AllowPipelineDiscovery, [switch]$AllowShaderMisses)
$root = Split-Path $PSScriptRoot -Parent
# Setup must tolerate route-coverage pack misses (issue #316).
if (-not $AllowShaderMisses) { throw 'graphics setup must allow route shader misses' }
Add-Content (Join-Path $root 'calls.txt') $(if ($ShaderMissDir) { "$Scale+misses" } else { $Scale })
$work = Join-Path $root $WorkRoot
$cache = Join-Path $work 'strict-state/cache'
[void][IO.Directory]::CreateDirectory((Join-Path $cache 'shaders/shareable'))
[IO.File]::WriteAllText((Join-Path $cache 'fh1-native-shaders-v2.bin'), 'analysis')
if ($env:PINYON_TEST_FAIL -eq '1') { throw 'simulated producer interruption' }
foreach ($file in @('fh1-gpu-prewarm-v3.txt', 'fh1-native-pipelines-v1.bin', "shaders/shareable/test-$Scale.pnsp")) {
    [IO.File]::WriteAllText((Join-Path $cache $file), 'validated artifact')
}
'{"result":"shaders-validated"}' | Set-Content (Join-Path $work 'production.json')
''')
            (root / "tools/prepare-fh1-vulkan.ps1").write_text(r'''
param($StateRoot, $GameRoot, $BuildDirectory, [switch]$JsonEvents)
$root = Split-Path $PSScriptRoot -Parent
Add-Content (Join-Path $root 'calls.txt') 'vulkan'
if ($env:PINYON_TEST_VULKAN_FAIL -eq 'stop') { [Environment]::Exit(1) }
if ($env:PINYON_TEST_VULKAN_FAIL -eq '1') { return }
$shareable = Join-Path $StateRoot 'cache/shaders/shareable'
[void][IO.Directory]::CreateDirectory($shareable)
[IO.File]::WriteAllText((Join-Path $shareable '4D5309C9.fbo.vk.xpso'), 'pipelines')
''')
            state = root / "state"
            save = state / "user/ForzaProfile/ForzaProfile"
            save.parent.mkdir(parents=True)
            save.write_bytes(b"untouched save")
            environment = os.environ.copy()
            environment.update(PINYON_TEST_ROOT=str(root), PINYON_TEST_DRIVER="one")
            command = r'''
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Management/Microsoft.PowerShell.Management.psd1')
function Get-CimInstance { [pscustomobject]@{ PNPDeviceID = 'test GPU'; DriverVersion = $env:PINYON_TEST_DRIVER } }
function Get-Process { return $null }
& (Join-Path $env:PINYON_TEST_ROOT 'tools/prepare-fh1-shaders.ps1') -StateRoot (Join-Path $env:PINYON_TEST_ROOT 'state') -JsonEvents
'''

            def run(success=True):
                result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                        env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                self.assertEqual(save.read_bytes(), b"untouched save")
                return result

            def calls():
                return (root / "calls.txt").read_text().splitlines()

            active = state / "cache/fh1-artifacts.json"
            # Vulkan, the default (and what any config before schema 28
            # migrates to), keeps the shaders and pipelines it creates as it
            # runs; its storage is filled once before the first start. A
            # failed preparation, or one stopped with the launcher's Cancel,
            # is not retried until the build changes (#389).
            environment["PINYON_TEST_VULKAN_FAIL"] = "stop"
            run(success=False)
            environment["PINYON_TEST_VULKAN_FAIL"] = "1"
            run()
            self.assertEqual(calls(), ["vulkan"])
            executable = root / "out/build/win-amd64-release/pinyon_shift.exe"
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text("rebuilt")
            environment["PINYON_TEST_VULKAN_FAIL"] = "0"
            run()
            run()
            self.assertEqual(calls(), ["vulkan", "vulkan"])
            self.assertFalse(active.exists())
            (root / "calls.txt").unlink()
            # A saved Direct3D 12 choice must not prepare legacy packs during
            # ordinary launch, even before the game's migration runs.
            (state / "config").mkdir()
            config = state / "config/pinyon_shift.toml"
            d3d12 = 'pinyon_shift_config_schema = 27\ngpu_backend = "d3d12"\n'
            config.write_text(d3d12)
            run()
            self.assertFalse(active.exists())
            self.assertFalse((root / "calls.txt").exists())
            # The unsupported developer switch retains the legacy tooling.
            command = command.replace(" -JsonEvents", " -LegacyD3D12 -JsonEvents")
            run()
            self.assertTrue(active.is_file())
            self.assertEqual(calls(), ["1"])
            run()
            # Writing the default settings must not invalidate preparation.
            config.write_text(d3d12 + "draw_resolution_scale_x = 1\ndraw_resolution_scale_y = 1\n")
            run()
            self.assertEqual(calls(), ["1"])
            (state / "cache/fh1-native-shaders-v2.bin").write_text("damaged")
            run()
            self.assertEqual((state / "cache/fh1-native-shaders-v2.bin").read_text(), "analysis")
            self.assertEqual(calls(), ["1"])
            previous = active.read_bytes()
            environment.update(PINYON_TEST_DRIVER="two", PINYON_TEST_FAIL="1")
            self.assertIn("simulated producer interruption", run(False).stderr)
            self.assertEqual(active.read_bytes(), previous)
            environment["PINYON_TEST_FAIL"] = "0"
            run()
            self.assertEqual(calls(), ["1", "1", "1"])
            config.write_text(d3d12 + "draw_resolution_scale_x = 2\ndraw_resolution_scale_y = 2\n")
            run()
            self.assertEqual(calls()[-1], "2")
            receipt = json.loads(active.read_text())
            self.assertEqual(len(receipt["files"]), 4)
            # A forged traversal is rejected and replaced with the validated set.
            receipt["files"][0]["path"] = "../../user/ForzaProfile/ForzaProfile"
            active.write_text(json.dumps(receipt))
            run()
            self.assertEqual(calls(), ["1", "1", "1", "2"])
            legacy = state / "cache/shaders/shareable"
            legacy.mkdir(parents=True, exist_ok=True)
            (legacy / "4D5309C9.xsh").write_bytes(b"shader")
            (legacy / "4D5309C9.rtv.d3d12.xpso").write_bytes(b"pipeline")
            run()
            run()
            self.assertEqual(calls(), ["1", "1", "1", "2", "2"])
            (legacy / "4D5309C9.xsh").write_bytes(b"more shaders")
            run()
            self.assertEqual(calls(), ["1", "1", "1", "2", "2", "2"])
            # Rebuilt binaries and sources outside the graphics inputs keep the
            # prepared graphics; a translator change prepares them again.
            for binary in ("pinyon_shift.exe", "rexgpu-fh1.dll", "rexruntime.dll"):
                (root / "out/build/win-amd64-release" / binary).write_text("rebuilt")
            (root / ".local/rexglue" / "src/graphics/pipeline/shader/spirv_translator.cpp").write_text("edited")
            run()
            self.assertEqual(len(calls()), 6)
            (root / ".local/rexglue" / "src/graphics/pipeline/shader/dxbc_translator.cpp").write_text("edited")
            run()
            run()
            self.assertEqual(len(calls()), 7)
            # A pack miss the game recorded prepares the pack again with it.
            misses = state / "cache/fh1-shader-misses"
            misses.mkdir()
            (misses / "vertex-AFF858C659830DD3-0000000000000001.bin").write_bytes(b"ucode")
            run()
            run()
            self.assertEqual(calls()[-1], "2+misses")
            self.assertEqual(len(calls()), 8)
            # Preparing every scale stages the other scales' packs too, once,
            # and keeps the chosen scale's set active (NP-4.7).
            config.write_text(d3d12 + "draw_resolution_scale_x = 2\ndraw_resolution_scale_y = 2\n"
                              "pinyon_shift_prepare_all_scales = true\n")
            run()
            self.assertEqual(calls()[8:], ["1+misses", "3+misses", "4+misses"])
            for scale in (1, 2, 3, 4):
                self.assertTrue((state / f"cache/shaders/shareable/test-{scale}.pnsp").is_file())
            self.assertIn("test-2.pnsp", active.read_text())
            run()
            self.assertEqual(len(calls()), 11)



ROUTE_VERDICT_COMMAND = r'''
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Load only the production script's top-level functions; nothing else runs.
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:PINYON_TEST_SCRIPT, [ref]$null, [ref]$null)
foreach ($function in $ast.FindAll({ param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([ScriptBlock]::Create($function.Extent.Text))
}
$launch = $env:PINYON_TEST_LAUNCH | ConvertFrom-Json
try {
    $verdict = Get-CompilerFreeRouteVerdict $env:PINYON_TEST_STATE $launch ([int64]$env:PINYON_TEST_ENTRIES) `
        ($env:PINYON_TEST_ALLOW -eq '1')
    [Console]::Out.Write(($verdict | ConvertTo-Json -Depth 6 -Compress))
} catch {
    [Console]::Out.Write(([ordered]@{ error = $_.Exception.Message
        build_log = $_.Exception.Data['build_log']; exit_code = $_.Exception.Data['exit_code']
        step = $_.Exception.Data['step']; excerpt = @($_.Exception.Data['error_excerpt']) } |
        ConvertTo-Json -Compress))
}
'''


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
class CompilerFreeRouteVerdictTests(unittest.TestCase):
    """Issue #316: route misses on another GPU must not fail graphics setup,
    and a real failure must say what failed and where the log is."""

    PACK_ENTRIES = 24862
    NORMAL = {"result": "normal-exit", "process_id": 7, "exit_code": 0}

    def run_verdict(self, state, launch=None, allow=True, entries=PACK_ENTRIES):
        environment = os.environ.copy()
        environment.update(
            PINYON_TEST_SCRIPT=str(ROOT / "tools/produce-fh1-artifacts.ps1"),
            PINYON_TEST_STATE=str(state), PINYON_TEST_ENTRIES=str(entries),
            PINYON_TEST_LAUNCH=json.dumps(launch or self.NORMAL),
            PINYON_TEST_ALLOW="1" if allow else "0",
        )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", ROUTE_VERDICT_COMMAND],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def make_state(self, root, *, complete=True, loaded=PACK_ENTRIES, ignored=None,
                   misses=(), records=(), draws=1200):
        state = pathlib.Path(root) / "strict-state"
        logs = state / "logs"
        logs.mkdir(parents=True)
        events = []
        if complete:
            events.append({"event": "fh1.render_test.complete", "frame": "7260"})
        else:
            events.append({"event": "fh1.render_test.failure", "reason": "capture_failed"})
        (logs / "20260930T000000Z-p7.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        lines = ["[info] FH1 native executor enabled: native"]
        if ignored:
            lines.append(f"[warning] Ignoring FH1 precompiled shader pack x.pnsp: {ignored}")
        if loaded is not None:
            lines.append(f"[info] Loaded {loaded} FH1 precompiled shaders from x.pnsp")
        lines += [f"[error] FH1 precompiled shader pack miss for {miss}" for miss in misses]
        lines.append(f"[info] FH1 native executor frame=9000 draws={draws} resolves=10")
        (logs / "runtime.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if records:
            directory = state / "cache/fh1-shader-misses"
            directory.mkdir(parents=True)
            for name in records:
                (directory / name).write_bytes(b"")
        return state

    def test_clean_route_passes_without_a_warning(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            verdict = self.run_verdict(self.make_state(directory), allow=False)
            self.assertIsNone(verdict["warning"])
            self.assertEqual(verdict["shader_misses"]["count"], 0)
            self.assertEqual(verdict["execution"]["draws"], 1200)
            self.assertEqual(verdict["exit_code"], 0)

    def test_route_misses_are_a_counted_warning_during_setup(self):
        misses = ("1111111111111111/0000000000000007", "2222222222222222/000000000000003F",
                  "geometry shader 00000012", "1111111111111111/0000000000000007")
        records = ("vertex-1111111111111111-0000000000000007.bin",
                   "pixel-2222222222222222-000000000000003F.bin",
                   "geometry-0000000000000000-0000000000000012.bin")
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            state = self.make_state(directory, misses=misses, records=records)
            verdict = self.run_verdict(state)
            found = verdict["shader_misses"]
            self.assertEqual((found["count"], found["vertex"], found["pixel"], found["geometry"]),
                             (3, 1, 1, 1))
            self.assertTrue(found["tolerated"])
            self.assertIn("1111111111111111/0000000000000007", found["examples"])
            self.assertIn("3 shader variants missing from the pack", verdict["warning"])
            self.assertIn("1 vertex, 1 pixel, 1 geometry", verdict["warning"])
            self.assertTrue(pathlib.Path(verdict["runtime_log"]).samefile(state / "logs/runtime.log"))

            # A maintainer's strict production still rejects them, with detail.
            failure = self.run_verdict(state, allow=False)
            self.assertIn("3 shader variants missing from the pack", failure["error"])
            self.assertIn("Route result: normal-exit, exit code 0", failure["error"])
            self.assertIn("Runtime log:", failure["error"])
            self.assertTrue(pathlib.Path(failure["build_log"]).samefile(state / "logs/runtime.log"))
            self.assertEqual(failure["exit_code"], 0)
            self.assertEqual(failure["step"], "compiler-free route check")
            self.assertIn("FH1 precompiled shader pack miss for geometry shader 00000012",
                          failure["excerpt"])

    def test_pack_that_did_not_load_stays_fatal_and_names_the_reason(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            state = self.make_state(directory, loaded=None, ignored="configuration mismatch",
                                    misses=("1111111111111111/0000000000000007",))
            failure = self.run_verdict(state)
            self.assertIn("did not load the produced shader pack", failure["error"])
            self.assertIn("configuration mismatch", failure["error"])
            self.assertIn("configuration mismatch", failure["excerpt"][0])
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            failure = self.run_verdict(self.make_state(directory, loaded=12))
            self.assertIn(f"it loaded 12 of {self.PACK_ENTRIES} shaders", failure["error"])
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            failure = self.run_verdict(self.make_state(directory, loaded=None))
            self.assertIn("did not find the staged pack", failure["error"])

    def test_crashes_and_incomplete_routes_report_exit_code_and_log(self):
        crash = {"result": "crash", "process_id": 7, "exit_code": -1073741819,
                 "crash_id": "c1", "bundle": "C:/crash/c1.zip"}
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            state = self.make_state(directory)
            failure = self.run_verdict(state, launch=crash)
            self.assertIn("The compiler-free route failed.", failure["error"])
            self.assertIn("exit code -1073741819", failure["error"])
            self.assertIn("C:/crash/c1.zip", failure["error"])
            self.assertEqual(failure["exit_code"], -1073741819)
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            failure = self.run_verdict(self.make_state(directory, complete=False))
            self.assertIn("did not complete (capture_failed)", failure["error"])
            self.assertIn("Runtime log:", failure["error"])
        with tempfile.TemporaryDirectory(prefix="pinyon-route-") as directory:
            failure = self.run_verdict(self.make_state(directory, draws=0))
            self.assertIn("did not execute the route", failure["error"])

    def test_logged_native_commands_tolerate_stderr_warnings(self):
        # Windows PowerShell turns redirected stderr into a terminating error
        # under 'Stop'; a CMake or compiler warning must not fail setup.
        with tempfile.TemporaryDirectory(prefix="pinyon-native-") as directory:
            log = pathlib.Path(directory) / "build.log"
            command = ROUTE_VERDICT_COMMAND.split("$launch =")[0] + r'''
$codes = @(
    (Invoke-LoggedNative $env:PINYON_TEST_LOG { cmd /c "echo warning from the build 1>&2" }),
    (Invoke-LoggedNative $env:PINYON_TEST_LOG { cmd /c "echo failed 1>&2 & exit 3" }),
    (Invoke-LoggedNative $env:PINYON_TEST_LOG { & 'pinyon-command-that-does-not-exist' }))
[Console]::Out.Write($codes -join ',')
'''
            environment = os.environ.copy()
            environment.update(PINYON_TEST_SCRIPT=str(ROOT / "tools/produce-fh1-artifacts.ps1"),
                               PINYON_TEST_LOG=str(log))
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "0,3,-1")
            self.assertTrue(log.is_file())

    def test_route_launches_use_the_long_hang_guard(self):
        script = (ROOT / "tools/produce-fh1-artifacts.ps1").read_text(encoding="utf-8")
        self.assertIn("RenderTestTimeoutSeconds = $RouteTimeoutSeconds", script)
        self.assertRegex(script, r"\[int\]\$RouteTimeoutSeconds = (\d{4,})")
        self.assertGreaterEqual(
            int(re.search(r"\[int\]\$RouteTimeoutSeconds = (\d+)", script).group(1)), 1800)


class ShaderPreparationKeyInputTests(unittest.TestCase):
    def test_every_hashed_repository_file_exists(self):
        # A deleted key input would make every real preparation fail.
        script = (ROOT / "tools/prepare-fh1-shaders.ps1").read_text(encoding="utf-8")
        start = script.index("'config/release-toolchain.json'")
        end = script.index("$legacyShaderCache")
        section = script[start:end]
        names = re.findall(r"'((?:config|tools|src)/[^'$]+)'", section)
        names += [f"{SDK}/{name}" for name in re.findall(r'"\$sdk/([^"$]+)"', section)]
        sdk_block = section[section.index("'fh1_shader_pack'"):
                            section.index("$graphicsSources.AddRange")]
        for name in re.findall(r"'([a-z0-9_/]+)'", sdk_block):
            names += [f"{SDK}/include/rex/graphics/{name}.h", f"{SDK}/src/graphics/{name}.cpp"]
        missing = [name for name in names if not (ROOT / name).exists()]
        self.assertGreater(len(names), 30)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
