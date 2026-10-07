<#
.SYNOPSIS
Builds and runs the host-side C++ tests without game files (NP-X).

.DESCRIPTION
Configures a build with PINYON_SHIFT_HOST_TESTS_ONLY, which needs no
generated game code, builds the pinyon_shift_host_tests target (the SDK
runtime, every host test and the sample mod) and the GPU plugin with the
Vulkan backend on, and runs the tests that need no game data. The
shader-pack test needs a prepared pack and is only compiled.
CI runs it after tools/provision-toolchain.ps1; locally it uses the
provisioned toolchain as the other build scripts do.
#>
[CmdletBinding()]
param(
    [string]$BuildDirectory = 'out/build/ci-host-tests',
    [ValidateSet('Release', 'RelWithDebInfo', 'Debug')]
    [string]$Configuration = 'Release'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$environment = Enter-PinyonBuildEnvironment
Push-Location $root
try {
    $sdk = Join-Path $root 'thirdparty/shiftglue-sdk'
    $arguments = @(
        '-S', '.', '-B', $BuildDirectory, '-G', 'Ninja',
        "-DCMAKE_MAKE_PROGRAM=$($environment.Ninja)",
        "-DCMAKE_BUILD_TYPE=$Configuration",
        '-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++',
        '-DCMAKE_C_FLAGS=-msse4.1', '-DCMAKE_CXX_FLAGS=-msse4.1',
        '-DPINYON_SHIFT_CPU_BASELINE=sse4.1',
        "-DREXSDK_DIR=$sdk",
        '-DPINYON_SHIFT_HOST_TESTS_ONLY=ON',
        # The Vulkan backend only builds here, so it does not drift (NP-12.3).
        '-DREXGLUE_USE_VULKAN=ON',
        # glslang reads its version through Python; a pyenv shim breaks that.
        "-DPYTHON_EXECUTABLE=$(Get-PinyonPython)")
    & $environment.CMake @arguments
    if ($LASTEXITCODE -ne 0) { throw "Configuring the host tests failed ($LASTEXITCODE)." }
    & $environment.CMake --build $BuildDirectory --target pinyon_shift_host_tests
    if ($LASTEXITCODE -ne 0) { throw "Building the host tests failed ($LASTEXITCODE)." }
    & $environment.CMake --build $BuildDirectory --target rexgpu-fh1
    if ($LASTEXITCODE -ne 0) { throw "Building the GPU plugin with Vulkan failed ($LASTEXITCODE)." }

    # Tests that link the SDK runtime load its DLL from the artifacts folder.
    $artifacts = [IO.Path]::GetFullPath((Join-Path $BuildDirectory 'rexglue-artifacts'))
    $env:PATH = "$artifacts;$env:PATH"
    $failed = @()
    foreach ($test in @(
            'pinyon_shift_fh1_ui_api_tests',
            'pinyon_shift_hostui_tests',
            'pinyon_shift_host_config_tests',
            'pinyon_shift_profile_body_tests',
            'pinyon_shift_rally_progress_tests',
            'pinyon_shift_rally_pace_tests',
            'pinyon_shift_car_cards_tests',
            'pinyon_shift_save_backups_tests',
            'pinyon_shift_content_roots_tests',
            'pinyon_shift_overlay_device_tests',
            'pinyon_shift_fh1_edram_tiles_tests')) {
        $exe = Join-Path $BuildDirectory "$test.exe"
        Write-Host "== $test"
        & $exe
        if ($LASTEXITCODE -ne 0) { $failed += $test }
    }
    if ($failed) { throw "Host tests failed: $($failed -join ', ')" }
    Write-Host 'Host tests passed.'
} finally {
    Pop-Location
}
