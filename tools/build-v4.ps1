[CmdletBinding()]
param(
    # The state root holding the player's verified update in title-update-v4/
    # (tools/verify-fh1-title-update.py --install).
    [Parameter(Mandatory)] [string]$StateRoot,
    # The extracted USA disc; defaults to .local/game/base.
    [string]$GameRoot,
    # 0 picks a job count from the logical processors and installed memory.
    [ValidateRange(0, 32)] [int]$Parallel = 0,
    # As in build-preview.ps1: 'auto' adds FMA3 when this CPU has it (#744).
    [ValidateSet('auto', 'sse4.1', 'fma', 'v3')]
    [string]$CpuBaseline = 'auto'
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

# Configure reads the generated tree's sources.cmake, so a first v4 build
# generates it here; later builds regenerate through the build's own
# dependency-tracked step (#540). The generator is the one the base build
# made.
$generatedRoot = Resolve-PinyonLocalPath -RelativePath '.local/generated-v4'
$generatedTrees = @('default', 'speech', 'xmedia')
$requiresBootstrap = -not (Test-Path -LiteralPath (Join-Path $generatedRoot 'default/codegen.build.stamp') -PathType Leaf)
foreach ($tree in $generatedTrees) {
    if (-not (Test-Path -LiteralPath (Join-Path $generatedRoot "$tree/sources.cmake") -PathType Leaf)) {
        $requiresBootstrap = $true
    }
}
if ($requiresBootstrap) {
    $rexglueExe = Join-Path (Resolve-PinyonRexGlueRoot) 'out/win-amd64/Release/rexglue.exe'
    if (-not (Test-Path -LiteralPath $rexglueExe -PathType Leaf)) {
        throw 'The ReXGlue generator is missing. Build the base game first (tools/build-preview.ps1).'
    }
    [void](New-Item -ItemType Directory -Force -Path $generatedRoot)
    $codegenLog = Join-Path $logs 'codegen-v4.log'
    $codegenConsoleLog = Join-Path $logs 'codegen-v4-console.log'
    if (Test-Path -LiteralPath $codegenLog) { Remove-Item -LiteralPath $codegenLog -Force }
    $codegenArguments = @('--log-level', 'info', '--log-file', $codegenLog, 'codegen',
        (Join-Path $root 'config/rexglue/pinyon_shift_v4_manifest.toml'), '--xex_apply_patches=true')
    Invoke-PinyonLoggedCommand -FilePath $rexglueExe -Arguments $codegenArguments `
        -LogPath $codegenConsoleLog -Utf8Output | Out-Host
    $codegenExit = $LASTEXITCODE
    if ($codegenExit -ne 0) {
        foreach ($tree in $generatedTrees) {
            $stamp = Join-Path $generatedRoot "$tree/codegen.build.stamp"
            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
        }
        throw (New-PinyonCommandFailure -FailureMessage 'v4 code generation failed; incomplete generation stamps were removed.' `
            -Step 'Translate the v4 game code' -LogPath $codegenConsoleLog -ExitCode $codegenExit `
            -CommandLine (Format-PinyonCommandLine -FilePath $rexglueExe -Arguments $codegenArguments))
    }
}
# A release install keeps the SDK in .local/rexglue, not in the submodule
# path the preset names (#459).
$cpu = Select-PinyonCpuBaseline -CpuBaseline $CpuBaseline
Write-Host "CPU baseline: $($cpu.Baseline)."
Invoke-PinyonBuildCommand $environment.CMake (@('--preset', 'win-amd64-v4',
    "-DREXSDK_DIR=$(Resolve-PinyonRexGlueRoot)") + $cpu.CMakeArguments +
    @("-DPYTHON_EXECUTABLE=$(Get-PinyonPython)")) `
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
[void](Write-PinyonBuildInfo -BuildDirectory $built -Variant 'v4' -Cpu $cpu `
    -AnalysisDirectory (Join-Path $root 'config/rexglue/analysis-v4'))
Write-Host "v4 build ready: $built\pinyon_shift.exe"
