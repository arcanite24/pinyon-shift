[CmdletBinding()]
param(
    [ValidateSet('Release')]
    [string]$Configuration = 'Release',
    [string]$GameRoot,
    [string]$StateRoot,
    [switch]$Json,
    [switch]$CrashSelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$executable = Join-Path $repoRoot 'out/build/win-amd64-release/pinyon_shift.exe'
$resolvedGameRoot = if ($GameRoot) {
    (Resolve-Path -LiteralPath $GameRoot).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $repoRoot '.local/game/base')).Path
}
$resolvedStateRoot = if ($StateRoot) {
    [IO.Path]::GetFullPath($StateRoot)
} else {
    Join-Path $repoRoot '.local/preview'
}

if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'The preview has not been built. Run tools/setup-preview.ps1 first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedGameRoot 'default.xex') -PathType Leaf)) {
    throw "The verified game files are missing: $resolvedGameRoot"
}
if (@(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Pinyon Shift is already running.'
}

foreach ($directory in @('', 'cache', 'config', 'crashes', 'logs', 'reports', 'update', 'user')) {
    $path = if ($directory) { Join-Path $resolvedStateRoot $directory } else { $resolvedStateRoot }
    [void](New-Item -ItemType Directory -Force -Path $path)
}
$pendingReport = Join-Path $resolvedStateRoot 'reports/pending-report.json'
if (Test-Path -LiteralPath $pendingReport -PathType Leaf) {
    Remove-Item -LiteralPath $pendingReport -Force
}

$savedStateRoot = $env:PINYON_SHIFT_STATE_ROOT
$savedGameRoot = $env:PINYON_SHIFT_GAME_ROOT
$savedTearing = $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING
$savedCrashTest = $env:PINYON_SHIFT_CRASH_SELF_TEST
$startedUtc = [DateTime]::UtcNow
$process = $null
try {
    $env:PINYON_SHIFT_STATE_ROOT = $resolvedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $resolvedGameRoot
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = 'false'
    $env:PINYON_SHIFT_CRASH_SELF_TEST = if ($CrashSelfTest) { '1' } else { $null }
    $process = Start-Process -FilePath $executable `
        -WorkingDirectory (Split-Path $executable -Parent) -PassThru
    $process.WaitForExit()
    $process.Refresh()
}
finally {
    $env:PINYON_SHIFT_STATE_ROOT = $savedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $savedGameRoot
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = $savedTearing
    $env:PINYON_SHIFT_CRASH_SELF_TEST = $savedCrashTest
}

if ($null -eq $process) { throw 'Windows did not start Pinyon Shift.' }
$exitCode = [int64]$process.ExitCode
if ($exitCode -ne 0) {
    $report = & (Join-Path $PSScriptRoot 'create-crash-report.ps1') `
        -StateRoot $resolvedStateRoot -Executable $executable `
        -StartedUtc $startedUtc -ProcessId $process.Id -ExitCode $exitCode -Json |
        ConvertFrom-Json
    $result = [ordered]@{
        result = 'crash'
        process_id = $process.Id
        exit_code = $exitCode
        crash_id = $report.crash_id
        bundle = $report.bundle
        issue_url = $report.issue_url
    }
    if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
    exit 1
}

$result = [ordered]@{
    result = 'normal-exit'
    process_id = $process.Id
    exit_code = $exitCode
}
if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
