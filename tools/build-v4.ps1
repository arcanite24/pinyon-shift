[CmdletBinding()]
param(
    # The state root holding the player's verified update in title-update-v4/
    # (tools/verify-fh1-title-update.py --install).
    [Parameter(Mandatory)] [string]$StateRoot,
    # The extracted USA disc; defaults to .local/game/base.
    [string]$GameRoot,
    # 0 picks a job count from the logical processors and installed memory.
    [ValidateRange(0, 32)] [int]$Parallel = 0
)

# Builds the FH1 v4 title-update executable (docs/TITLE_UPDATE_V4_BACKLOG.md)
# into out/build/win-amd64-v4. The generator applies the player's patches to
# copies of the disc executables in .local/game/v4-codegen; the disc folder,
# the update package and the base build are left untouched.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$resolvedGameRoot = if ($GameRoot) { [IO.Path]::GetFullPath($GameRoot) } else { Join-Path $root '.local/game/base' }
$update = Join-Path ([IO.Path]::GetFullPath($StateRoot)) 'title-update-v4'
$modules = 'default', 'SpeechFacade_default', 'XMediaFacade_default'
foreach ($module in $modules) {
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedGameRoot "$module.xex") -PathType Leaf)) {
        throw "The disc executable $module.xex is missing from $resolvedGameRoot."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $update "$module.xexp") -PathType Leaf)) {
        throw "Install the verified title update first (tools/verify-fh1-title-update.py --install)."
    }
}

$codegen = Resolve-PinyonLocalPath -RelativePath '.local/game/v4-codegen'
[void](New-Item -ItemType Directory -Force -Path $codegen)
foreach ($module in $modules) {
    Copy-Item -LiteralPath (Join-Path $resolvedGameRoot "$module.xex") -Destination $codegen -Force
    Copy-Item -LiteralPath (Join-Path $update "$module.xexp") -Destination $codegen -Force
}

$environment = Enter-PinyonBuildEnvironment
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)
if ($Parallel -eq 0) { $Parallel = Get-PinyonBuildJobCount }
Invoke-PinyonBuildCommand $environment.CMake @('--preset', 'win-amd64-v4',
    "-DPYTHON_EXECUTABLE=$(Get-PinyonPython)") `
    (Join-Path $logs 'v4-configure.log') 'v4 configuration failed.' -Step 'Configure the v4 build'
Invoke-PinyonBuildCommand $environment.CMake @('--build', 'out/build/win-amd64-v4', '--parallel', "$Parallel",
    '--target', 'pinyon_shift', 'pinyon_shift_fh1_archive_extract') `
    (Join-Path $logs 'v4-build.log') 'v4 build failed.' -Step 'Build the v4 executable'
$built = Join-Path $root 'out/build/win-amd64-v4'
foreach ($library in Get-ChildItem -LiteralPath (Join-Path $built 'rexglue-artifacts') -Filter '*.dll') {
    # The executable loads its runtime from its own folder.
    Copy-Item -LiteralPath $library.FullName -Destination $built -Force
}
& (Get-PinyonPython) (Join-Path $root 'tools/verify-codegen-log.py') (Join-Path $logs 'codegen-v4.log') `
    --allowlist (Join-Path $root 'config/rexglue/accepted-codegen-warnings-v4.json')
if ($LASTEXITCODE -ne 0) { throw 'The v4 code generation log has unreviewed warnings.' }
Write-Host "v4 build ready: $built\pinyon_shift.exe"
