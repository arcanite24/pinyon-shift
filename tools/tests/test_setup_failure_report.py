"""Setup failures must name the failed step and show its real error.

Issues 45, 62, 69 and 212 were first-time setup failures whose launcher
output ended in a wrapper message ("ReXGlue code-generator build failed.",
"ninja: build stopped: subcommand failed.") without the command that failed.
These tests run the PowerShell helpers that find the error in a complete log
and the CMake staging script that replaces the runtime DLLs.
"""

import ctypes
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")


def run_powershell(script, environment=None):
    command = ". ./tools/release-common.ps1\n$ErrorActionPreference = 'Stop'\n" + script
    env = os.environ.copy()
    env.update(environment or {})
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class FailureDetailTests(unittest.TestCase):
    def detail(self, lines):
        with tempfile.TemporaryDirectory(prefix="pinyon-failure-") as directory:
            log = pathlib.Path(directory) / "build.log"
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = run_powershell(
                "$d = Get-PinyonCommandFailureDetail -Lines (Read-PinyonLogLines -LogPath $env:PINYON_LOG)\n"
                "[Console]::Out.Write((ConvertTo-Json -InputObject ([ordered]@{"
                " kind = $d.Kind; excerpt = [string[]]$d.Excerpt; hint = $d.Hint;"
                " failed = $d.FailedCommands }) -Depth 3))",
                {"PINYON_LOG": str(log)},
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_first_ninja_failure_is_found_above_later_job_output(self):
        # Issue 212: the jobs still running after the failure printed screens
        # of warnings, so the tail of the output showed none of the error.
        lines = [f"[{n}/707] Building CXX object src/a{n}.cpp.obj" for n in range(1, 540)]
        lines += [
            "FAILED: src/system/CMakeFiles/rexruntime.dir/Release/xthread.cpp.obj",
            "C:\\llvm\\bin\\clang++.exe " + "-DDEFINE " * 200 + "-c xthread.cpp",
            "xthread.cpp(10,3): error: no member named 'boom' in 'rex::XThread'",
            "   10 |   boom();",
            "      |   ^",
            "1 error generated.",
        ]
        for n in range(541, 570):
            lines += [
                f"[{n}/707] Building CXX object src/input/b{n}.cpp.obj",
                f"b{n}.cpp:439:77: warning: unused parameter 'vibration' [-Wunused-parameter]",
                "  439 | X_RESULT f(int vibration) {",
                "1 warning generated.",
            ]
        lines.append("ninja: build stopped: subcommand failed.")
        detail = self.detail(lines)
        self.assertEqual(detail["kind"], "ninja")
        excerpt = detail["excerpt"]
        self.assertTrue(excerpt[0].startswith("FAILED: src/system/CMakeFiles/rexruntime.dir"))
        self.assertTrue(excerpt[1].endswith(" ..."), "very long command lines are shortened")
        self.assertLess(len(excerpt[1]), 700)
        self.assertIn("xthread.cpp(10,3): error: no member named 'boom' in 'rex::XThread'", excerpt)
        self.assertFalse(any("unused parameter" in line for line in excerpt))
        self.assertFalse(any("build stopped" in line for line in excerpt))

    def test_a_long_failed_block_keeps_its_error_lines(self):
        lines = ["[1/3] Building CXX object big.obj", "FAILED: big.obj", "clang++ -c big.cpp"]
        lines += [f"big.cpp:{n}:1: warning: unused variable 'x{n}'" for n in range(200)]
        lines += ["big.cpp:900:5: error: expected ';' after expression", "1 error generated."]
        lines += ["ninja: build stopped: subcommand failed."]
        detail = self.detail(lines)
        excerpt = detail["excerpt"]
        self.assertLessEqual(len(excerpt), 60)
        self.assertEqual(excerpt[:2], ["FAILED: big.obj", "clang++ -c big.cpp"])
        self.assertIn("big.cpp:900:5: error: expected ';' after expression", excerpt)

    def test_more_failures_are_counted_and_the_first_is_shown(self):
        lines = [
            "FAILED: a.obj", "clang++ -c a.cpp", "a.cpp:1:1: error: first",
            "[2/9] Building CXX object b.obj",
            "FAILED: b.obj", "clang++ -c b.cpp", "b.cpp:1:1: error: second",
            "ninja: build stopped: subcommand failed.",
        ]
        detail = self.detail(lines)
        self.assertEqual(detail["failed"], 2)
        self.assertIn("a.cpp:1:1: error: first", detail["excerpt"])
        self.assertNotIn("b.cpp:1:1: error: second", detail["excerpt"])
        self.assertIn("1 more command(s) failed", detail["excerpt"][-1])

    def test_cmake_configure_error_block_is_reported(self):
        # Issue 62: only "ReXGlue configuration failed." reached the report.
        lines = [
            "-- The C compiler identification is Clang 20.1.8",
            "-- Detecting C compiler ABI info",
            "CMake Error at CMakeLists.txt:12 (project):",
            "  No CMAKE_CXX_COMPILER could be found.",
            "",
            "  Tell CMake where to find the compiler by setting CMAKE_CXX_COMPILER.",
            "",
            "",
            "-- Configuring incomplete, errors occurred!",
        ]
        detail = self.detail(lines)
        self.assertEqual(detail["kind"], "cmake")
        self.assertEqual(detail["excerpt"][0], "CMake Error at CMakeLists.txt:12 (project):")
        self.assertIn("  No CMAKE_CXX_COMPILER could be found.", detail["excerpt"])
        self.assertNotIn("-- Configuring incomplete, errors occurred!", detail["excerpt"])
        self.assertIn("Build Tools", detail["hint"])

    def test_locked_runtime_copy_gets_a_plain_hint(self):
        # Issue 69: staging stopped with no visible error.
        lines = [
            "[1/3] Staging project gamepad mappings beside pinyon_shift",
            "[2/3] Staging the current ReXGlue runtime beside pinyon_shift",
            "FAILED: CMakeFiles/pinyon_shift_stage_rexruntime",
            'cmd.exe /C "cmake.exe -E copy_if_different rexruntime.dll out/rexruntime.dll"',
            'Error copying file (if different) from "rexruntime.dll" to "out/rexruntime.dll".',
            "ninja: build stopped: subcommand failed.",
        ]
        detail = self.detail(lines)
        self.assertIn('Error copying file (if different) from "rexruntime.dll" to "out/rexruntime.dll".',
                      detail["excerpt"])
        self.assertIn("another program has it open", detail["hint"])
        self.assertIn("antivirus", detail["hint"])

    def test_resource_failures_get_hints(self):
        for line, expected in (
            ("LLVM ERROR: out of memory", "ran out of memory"),
            ("lld-link: error: failed to write the output file: No space left on device", "free space"),
            ("lld-link: error: failed to write the output file: permission denied", "another program"),
            ("fatal error: error in backend: IO failure on output stream: No space left on device", "free space"),
            ("clang++: error: clang frontend command failed due to signal (use -v to see invocation)", "crashed"),
        ):
            with self.subTest(line=line):
                detail = self.detail(["FAILED: x.obj", "clang++ -c x.cpp", line])
                self.assertIn(expected, detail["hint"])

    def test_logs_without_markers_fall_back_to_error_lines(self):
        lines = ["Cloning into 'thirdparty/sdl3'..."] + [f"progress {n}" for n in range(100)]
        lines += ["fatal: unable to access 'https://github.com/x/y/': Could not resolve host: github.com"]
        detail = self.detail(lines)
        self.assertEqual(detail["kind"], "errors")
        self.assertEqual(detail["excerpt"][-1],
                         "fatal: unable to access 'https://github.com/x/y/': Could not resolve host: github.com")
        self.assertNotIn("progress 3", detail["excerpt"])


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class BuildCommandFailureTests(unittest.TestCase):
    def test_missing_or_empty_log_preserves_original_failure(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-empty-log-") as directory:
            root = pathlib.Path(directory)
            for contents in (None, "", "single line\n"):
                with self.subTest(contents=contents):
                    log = root / "codegen.log"
                    if contents is not None:
                        log.write_text(contents, encoding="utf-8")
                    result = run_powershell(r"""
try {
    throw (New-PinyonCommandFailure -FailureMessage 'Original codegen failure' -Step 'Translate the game code' -LogPath $env:PINYON_LOG -ExitCode 9 -CommandLine 'rexglue codegen')
}
catch {
    $record = New-PinyonFailureRecord -ErrorRecord $_
    [Console]::Out.Write(($record | ConvertTo-Json -Depth 4))
}
""", {"PINYON_LOG": str(log)})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    record = json.loads(result.stdout)
                    self.assertIn("Original codegen failure", record["message"])
                    self.assertEqual(record["exit_code"], 9)
                    self.assertEqual(record["step"], "Translate the game code")
                    self.assertEqual(record["error_excerpt"], [] if not contents else ["single line"])

    def test_codegen_console_error_survives_missing_native_log(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-codegen-console-") as directory:
            root = pathlib.Path(directory)
            fake = root / "fake_codegen.py"
            fake.write_text("import sys\nprint('Failed: example.toml is not a manifest: no [project] section.')\nsys.exit(3)\n")
            log = root / "codegen-console.log"
            report = root / "report.json"
            result = run_powershell(r"""
Invoke-PinyonLoggedCommand -FilePath $env:PINYON_PYTHON -Arguments @($env:PINYON_FAKE) -LogPath $env:PINYON_LOG | Out-Null
$codegenExit = $LASTEXITCODE
try {
    throw (New-PinyonCommandFailure -FailureMessage 'Local code generation failed' -Step 'Translate the game code' -LogPath $env:PINYON_LOG -ExitCode $codegenExit)
}
catch {
    $record = New-PinyonFailureRecord -ErrorRecord $_
    [IO.File]::WriteAllText($env:PINYON_REPORT, ($record | ConvertTo-Json -Depth 4))
}
""", {"PINYON_PYTHON": sys.executable, "PINYON_FAKE": str(fake),
       "PINYON_LOG": str(log), "PINYON_REPORT": str(report)})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = json.loads(report.read_text(encoding="utf-8-sig"))
            self.assertEqual(record["exit_code"], 3)
            self.assertIn("no [project] section", record["error_excerpt"][0])
            self.assertIn("no [project] section", log.read_text())

    def test_failed_native_step_reports_step_exit_code_log_and_error(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-build-failure-") as directory:
            fake = pathlib.Path(directory) / "fake_ninja.py"
            fake.write_text(
                "import sys\n"
                "print('[1/3] Building CXX object a.obj', flush=True)\n"
                "print('FAILED: b.obj')\n"
                "print('clang++ -c b.cpp')\n"
                "print(\"b.cpp(3,1): error: use of undeclared identifier 'boom'\")\n"
                "for n in range(120): print(f'[{n}/3] c.cpp: warning: unused parameter')\n"
                "sys.stdout.flush()\n"
                "sys.stderr.write('ninja: build stopped: subcommand failed.\\n')\n"
                "sys.stderr.write('\\n')\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            log = pathlib.Path(directory) / "logs" / "preview-build.log"
            report = pathlib.Path(directory) / "setup-error.json"
            result = run_powershell(
                r"""
try {
    Invoke-PinyonBuildCommand $env:PINYON_PYTHON @($env:PINYON_FAKE) $env:PINYON_LOG 'Preview compilation failed.' -Step 'Compile the game' | Out-Null
    throw 'Failure was swallowed'
}
catch {
    if ($_.Exception.Message -eq 'Failure was swallowed') { throw }
    $record = New-PinyonFailureRecord -ErrorRecord $_
    [IO.File]::WriteAllText($env:PINYON_REPORT, ($record | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Format-PinyonFailureRecord -Record $record | ForEach-Object { [Console]::Out.WriteLine($_) }
}
""",
                {"PINYON_PYTHON": sys.executable, "PINYON_FAKE": str(fake),
                 "PINYON_LOG": str(log), "PINYON_REPORT": str(report)},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = json.loads(report.read_text(encoding="utf-8-sig"))
            log_text = log.read_text(encoding="utf-8")

        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["step"], "Compile the game")
        self.assertEqual(record["exit_code"], 1)
        self.assertEqual(record["build_log"], str(log))
        self.assertEqual(record["error_kind"], "ninja")
        self.assertIn(str(fake), record["command"])
        self.assertIn("b.cpp(3,1): error: use of undeclared identifier 'boom'", record["error_excerpt"])
        self.assertIn("Preview compilation failed. Exit code: 1.", record["message"])
        self.assertIsInstance(record["output_tail"], list)
        # stderr is kept as plain text; an empty stderr line is not the
        # exception type name.
        self.assertIn("ninja: build stopped: subcommand failed.", log_text)
        self.assertNotIn("RemoteException", log_text)
        self.assertIn("> exit code 1", log_text)
        printed = result.stdout
        self.assertIn("==================== SETUP FAILED", printed)
        self.assertIn("Failed step: Compile the game", printed)
        self.assertIn("Exit code: 1", printed)
        self.assertIn(f"Full log: {log}", printed)
        self.assertIn("    b.cpp(3,1): error: use of undeclared identifier 'boom'", printed)

    def test_single_line_excerpt_is_still_a_json_array(self):
        result = run_powershell(r"""
$failure = [Exception]::new('Unable to initialize the Microsoft x64 build environment.')
$failure.Data['step'] = 'Initialize the Microsoft x64 build environment'
$failure.Data['exit_code'] = 1
$failure.Data['error_excerpt'] = [string[]]@('[ERROR:VsDevCmd.bat] Script failed')
try { throw $failure } catch { [Console]::Out.Write((New-PinyonFailureRecord -ErrorRecord $_ | ConvertTo-Json -Depth 4)) }
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["error_excerpt"], ["[ERROR:VsDevCmd.bat] Script failed"])
        self.assertIn("Build Tools", record["hint"])

    def test_a_missing_program_is_a_failure_not_a_stale_success(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-missing-") as directory:
            result = run_powershell(r"""
cmd /c exit 0
try {
    Invoke-PinyonBuildCommand (Join-Path $env:PINYON_DIR 'missing.exe') @('--version') (Join-Path $env:PINYON_DIR 'x.log') 'Tool failed.' | Out-Null
    throw 'Failure was swallowed'
}
catch {
    if ($_.Exception.Data['exit_code'] -ne -1) { throw }
    [Console]::Out.Write(($_.Exception.Data['error_excerpt'] -join "`n"))
}
""", {"PINYON_DIR": directory})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("could not be started because it was not found", result.stdout)

    def test_parallel_jobs_are_capped_by_memory(self):
        result = run_powershell(r"""
$cases = @(
    @(24, 32GB), @(24, 16GB), @(24, 8GB), @(24, 4GB), @(24, 0), @(4, 64GB), @(1, 64GB)
)
($cases | ForEach-Object { Get-PinyonBuildJobCount -LogicalProcessors $_[0] -MemoryBytes $_[1] }) -join ','
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # 24 threads keep the 16-job cap with 32 GB; low-memory machines get
        # about 1.5 GB per job; unknown memory keeps the processor rule.
        self.assertEqual(result.stdout.strip(), "16,9,4,1,16,3,2")


def find_cmake():
    config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
    local = ROOT / config["cmake"]["install_path"] / config["cmake"]["executable"]
    return str(local) if local.is_file() else shutil.which("cmake")


@unittest.skipUnless(sys.platform == "win32" and find_cmake(), "Windows and CMake are required")
class StageFileScriptTests(unittest.TestCase):
    SCRIPT = ROOT / "cmake/PinyonStageFile.cmake"

    @staticmethod
    def lock(path):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                         ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateFileW(str(path), 0x80000000, 0x1, None, 3, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise OSError(ctypes.get_last_error(), "CreateFileW failed")
        return kernel32, handle

    def stage(self, source, destination, attempts):
        return subprocess.run(
            [find_cmake(), f"-DSOURCE={source}", f"-DDESTINATION={destination}",
             f"-DATTEMPTS={attempts}", "-P", str(self.SCRIPT)],
            capture_output=True, text=True,
        )

    def test_copies_only_when_different(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-stage-") as directory:
            source = pathlib.Path(directory) / "rexruntime.dll"
            destination = pathlib.Path(directory) / "out" / "rexruntime.dll"
            destination.parent.mkdir()
            source.write_bytes(b"new runtime")
            result = self.stage(source, destination, 2)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(destination.read_bytes(), b"new runtime")
            stamp = destination.stat().st_mtime_ns
            time.sleep(0.05)
            self.assertEqual(self.stage(source, destination, 2).returncode, 0)
            self.assertEqual(destination.stat().st_mtime_ns, stamp)

    def test_a_locked_destination_is_named_with_the_reason_and_fix(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-stage-") as directory:
            source = pathlib.Path(directory) / "rexruntime.dll"
            destination = pathlib.Path(directory) / "rexruntime-staged.dll"
            source.write_bytes(b"new runtime")
            destination.write_bytes(b"old runtime")
            kernel32, handle = self.lock(destination)
            try:
                result = self.stage(source, destination, 2)
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Could not replace rexruntime-staged.dll beside the game", output)
            self.assertIn("open in another program", output)
            self.assertIn(str(destination), output)
            self.assertEqual(destination.read_bytes(), b"old runtime")

    def test_a_briefly_locked_destination_is_retried(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-stage-") as directory:
            source = pathlib.Path(directory) / "rexgpu-fh1.dll"
            destination = pathlib.Path(directory) / "rexgpu-fh1-staged.dll"
            source.write_bytes(b"new backend")
            destination.write_bytes(b"old backend")
            kernel32, handle = self.lock(destination)
            # Release the lock once the script reports its first failed copy,
            # not on a timer: starting CMake on a CI runner can take longer
            # than any fixed delay, so the lock was gone before the first try.
            process = subprocess.Popen(
                [find_cmake(), f"-DSOURCE={source}", f"-DDESTINATION={destination}",
                 "-DATTEMPTS=8", "-P", str(self.SCRIPT)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            output = []
            try:
                for line in process.stdout:
                    output.append(line)
                    if handle is not None and "is in use" in line:
                        kernel32.CloseHandle(ctypes.c_void_p(handle))
                        handle = None
                returncode = process.wait(timeout=60)
            finally:
                if handle is not None:
                    kernel32.CloseHandle(ctypes.c_void_p(handle))
                process.stdout.close()
            output = "".join(output)
            self.assertEqual(returncode, 0, output)
            self.assertIn("is in use", output)
            self.assertIn("Staged rexgpu-fh1-staged.dll after 2 attempts.", output)
            self.assertEqual(destination.read_bytes(), b"new backend")


class SetupFailureContractTests(unittest.TestCase):
    def test_setup_reports_failures_without_rethrowing_through_write_error(self):
        setup = (ROOT / "tools/setup-preview.ps1").read_text(encoding="utf-8")
        catch = setup.split("\ncatch {", 1)[1]
        # Write-Error under 'Stop' became a terminating error positioned at
        # the Write-Error line ("At :92 char:5") instead of the failure.
        self.assertNotIn("Write-Error $_", catch)
        self.assertIn("New-PinyonFailureRecord -ErrorRecord $failure", catch)
        self.assertIn("Format-PinyonFailureRecord", catch)
        self.assertIn("exit 1", catch)
        # Early checks (ISO path, Windows build) are reported too.
        body = setup.split("\ntry {", 1)[1]
        self.assertIn("Resolve-Path -LiteralPath $IsoPath", body)
        self.assertIn("minimum_windows_build", body)
        self.assertIn("Remove-Item -LiteralPath $errorPath", setup.split("\ntry {", 1)[0])

    def test_every_native_build_step_is_named(self):
        build = (ROOT / "tools/build-preview.ps1").read_text(encoding="utf-8")
        calls = build.split("Invoke-PinyonBuildCommand")[1:]
        self.assertEqual(len(calls), 4)
        for call in calls:
            # Each call statement ends before the next line that starts code.
            statement = call.split("\n    Invoke-", 1)[0].split("\n}", 1)[0]
            self.assertIn("-Step '", statement)
        self.assertIn("New-PinyonCommandFailure", build)
        self.assertIn("Get-PinyonBuildJobCount", build)

    def test_runtime_staging_uses_the_retrying_script(self):
        rexglue = (ROOT / "cmake/PinyonShiftRexGlue.cmake").read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        staging = rexglue.split("_stage_rexruntime ALL", 1)[1].split("VERBATIM)", 1)[0]
        self.assertNotIn("copy_if_different", staging)
        self.assertEqual(staging.count("-P ${PINYON_SHIFT_STAGE_FILE_SCRIPT}"), 2)
        mappings = cmake.split("pinyon_shift_stage_controller_mappings ALL", 1)[1].split("VERBATIM)", 1)[0]
        self.assertIn('-P "${PINYON_SHIFT_STAGE_FILE_SCRIPT}"', mappings)

    def test_launcher_shows_the_failure_report_when_output_lacks_it(self):
        launcher = (ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml.cs").read_text(encoding="utf-8")
        common = (ROOT / "tools/release-common.ps1").read_text(encoding="utf-8")
        self.assertIn('"setup-error.json"', launcher)
        self.assertIn("DescribeSetupFailure(process.ExitCode, setupStartedUtc)", launcher)
        banner = launcher.split('SetupFailureBanner = "', 1)[1].split('"', 1)[0]
        self.assertIn(f"$lines.Add('{banner}", common)


if __name__ == "__main__":
    unittest.main()
