"""Exercise setup's real compiler against supported and incompatible headers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BuildCapabilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows build tools required")
    def test_selected_library_sdk_and_failure_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-capability-test-") as directory:
            root = Path(directory) / "headers (ñ)"
            library, sdk = root / "library", root / "sdk"
            library.mkdir(parents=True)
            sdk.mkdir()
            (library / "bit").write_text("namespace std {}\n")
            (sdk / "d3d12.h").write_text("#pragma once\n")
            environment = os.environ.copy()
            environment["PINYON_TEST_HEADERS"] = str(root)
            command = r'''
. ./tools/release-common.ps1
$ErrorActionPreference = 'Stop'
$environment = Enter-PinyonBuildEnvironment
$expectedInclude = $env:INCLUDE
$previousTemp = $env:TEMP
$env:TEMP = Join-Path $env:PINYON_TEST_HEADERS 'temp (ñ)'
New-Item -ItemType Directory -Path $env:TEMP | Out-Null
$expectedLib = $env:LIB
function Expect-CapabilityFailure([string]$Folder, [string]$Step, [string]$Symbol) {
    if ($Folder) { $env:INCLUDE = "$(Join-Path $env:PINYON_TEST_HEADERS $Folder);$expectedInclude" }
    try {
        Assert-PinyonBuildCapabilities -LlvmRoot $environment.LlvmRoot
        throw 'Incompatible headers were accepted'
    } catch {
        if ($_.Exception.Data['step'] -ne $Step) { throw }
        if ($_.Exception.Data['exit_code'] -eq 0) { throw 'Missing compiler failure' }
        if ($_.Exception.Data['error_kind'] -ne 'toolchain-capability') { throw 'Wrong error kind' }
        if (($_.Exception.Data['error_excerpt'] -join "`n") -notmatch $Symbol) { throw 'Compiler diagnostic lost' }
        if (-not $_.Exception.Data['hint']) { throw 'Update instructions lost' }
    }
    if (@(Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter 'pinyon-capabilities-*').Count) {
        throw 'Failed probe left temporary files'
    }
}
try {
    Expect-CapabilityFailure 'library' 'Check C++23 standard library' 'byteswap'
    Expect-CapabilityFailure 'sdk' 'Check Windows SDK headers' 'D3D12_FEATURE_DATA_D3D12_OPTIONS8'
    $env:INCLUDE = $expectedInclude
    # #379: SDK headers present, but LIB lacks the SDK import libraries.
    $env:LIB = (($expectedLib -split ';') | Where-Object { $_ -and -not (Test-Path -LiteralPath (Join-Path $_ 'kernel32.lib')) }) -join ';'
    Expect-CapabilityFailure '' 'Check Windows SDK libraries' 'kernel32'
    $env:LIB = $expectedLib
    Assert-PinyonBuildCapabilities -LlvmRoot $environment.LlvmRoot
    if (@(Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter 'pinyon-capabilities-*').Count) {
        throw 'Successful probe left temporary files'
    }
} finally {
    $env:INCLUDE = $expectedInclude
    $env:LIB = $expectedLib
    $env:TEMP = $previousTemp
}
'''
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    cwd=ROOT, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
