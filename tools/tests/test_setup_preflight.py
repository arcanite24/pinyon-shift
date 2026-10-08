"""Setup checks free space and the download sites before a long build (#393).

A full disk or a blocked download host used to surface only as a failed
step tens of minutes in. These run the PowerShell checks with the release
configuration overridden.
"""

import json
import os
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")


def run_powershell(script):
    command = ". ./tools/release-common.ps1\n$ErrorActionPreference = 'Stop'\n" + script
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )


def failure(script):
    """Runs a check and returns its failure's message and data as JSON."""
    result = run_powershell(
        "try {\n" + script + "\n[Console]::Out.Write('{}') }\n"
        "catch { $e = $_.Exception; [Console]::Out.Write((ConvertTo-Json -InputObject ([ordered]@{"
        " message = $e.Message; kind = $e.Data['error_kind']; step = $e.Data['step'];"
        " hint = $e.Data['hint'] }))) }")
    return json.loads(result.stdout or "null")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class PreflightTests(unittest.TestCase):
    def test_the_configured_figures_are_used(self):
        config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
        space = config["disk_space_gb"]
        self.assertGreater(space["first_build"], space["rebuild"])
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"{space['first_build']} GB", readme)

    def test_short_space_names_the_drive_and_the_need(self):
        # An impossible requirement on the install drive fails with the drive,
        # its free space and the figure.
        result = failure(
            "function Get-PinyonReleaseToolchain { [pscustomobject]@{ disk_space_gb ="
            " [pscustomobject]@{ first_build = 1000000; rebuild = 1; system_drive = 0;"
            " build_tools = 0 } } }\n"
            "Assert-PinyonFreeSpace -Root . -FirstBuild")
        self.assertEqual(result["kind"], "disk-space")
        self.assertIn("needs 1000000 GB", result["hint"])
        self.assertEqual(result["step"], "Check free disk space")

    def test_enough_space_passes(self):
        result = failure(
            "function Get-PinyonReleaseToolchain { [pscustomobject]@{ disk_space_gb ="
            " [pscustomobject]@{ first_build = 0; rebuild = 0; system_drive = 0;"
            " build_tools = 0 } } }\n"
            "Assert-PinyonFreeSpace -Root . -FirstBuild -BuildToolsMissing")
        self.assertEqual(result, {})

    def test_an_unreachable_host_is_named(self):
        result = failure("Assert-PinyonDownloadHosts -Uris @('https://pinyon-shift.invalid/tool.zip')")
        self.assertEqual(result["kind"], "network")
        self.assertIn("https://pinyon-shift.invalid", result["hint"])

    def test_nothing_to_download_checks_nothing(self):
        self.assertEqual(failure("Assert-PinyonDownloadHosts -Uris @()"), {})

    def test_setup_and_provisioning_run_the_checks(self):
        setup = (ROOT / "tools/setup-preview.ps1").read_text(encoding="utf-8")
        provision = (ROOT / "tools/provision-toolchain.ps1").read_text(encoding="utf-8")
        self.assertLess(setup.index("Assert-PinyonFreeSpace"), setup.index("provision-toolchain.ps1"))
        self.assertLess(provision.index("Assert-PinyonDownloadHosts"),
                        provision.index("Invoke-PinyonDownload"))

    def test_repair_updates_then_adds_each_component(self):
        # The elevated helper gets the component list as one comma-separated
        # argument; a restart request from any run is passed on (#393, #339).
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            temp = pathlib.Path(temp)
            log = temp / "calls.txt"
            fake = temp / "setup.cmd"
            fake.write_text(f'@echo %*>>"{log}"\r\n@exit /b 3010\r\n', encoding="ascii")
            result = subprocess.run(
                [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "tools/install-build-tools.ps1"), "-Bootstrapper", str(fake),
                 "-Mode", "Repair", "-InstallPath", str(temp / "Build Tools"),
                 "-Add", "A.One,B.Two"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 3010, result.stderr)
            calls = log.read_text(encoding="ascii").splitlines()
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].startswith("update --installPath"))
        self.assertIn("Build Tools", calls[0])
        self.assertIn("--add A.One --add B.Two", calls[1])
        self.assertIn("--passive", calls[1])

    def test_provisioning_repairs_once_and_asks_for_a_restart(self):
        provision = (ROOT / "tools/provision-toolchain.ps1").read_text(encoding="utf-8")
        config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
        self.assertIn("-Mode Repair", provision)
        self.assertIn("'reboot-required'", provision)
        self.assertIn("toolchain-capability", provision)
        self.assertEqual(provision.count("Enter-PinyonBuildEnvironment"), 2)
        self.assertTrue(any("WindowsSDK" in c or "Windows11SDK" in c
                            for c in config["visual_studio"]["repair_components"]))


if __name__ == "__main__":
    unittest.main()
