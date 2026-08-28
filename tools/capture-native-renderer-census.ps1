[CmdletBinding()]
param(
    [string]$StateRoot,
    [ValidateSet('unmarked', 'front_end', 'garage', 'open_world_day',
        'open_world_night', 'traffic', 'race', 'rewind', 'pause',
        'save_reload')]
    [string]$Scene = 'unmarked',
    [string]$ShaderCaptureDir,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$IndexScanSignature,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$TextureScanSignature,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$ReplaySnapshotSignature,
    [string]$ReplaySnapshotDir,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $StateRoot) {
    $sourceRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source'
    $profile = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq 'ForzaProfile' -and $_.Directory.Name -eq 'ForzaProfile' } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $profile) {
        throw "No installed preview ForzaProfile was found under $sourceRoot"
    }
    $separator = [IO.Path]::DirectorySeparatorChar
    $marker = "${separator}user${separator}"
    $markerIndex = $profile.FullName.IndexOf($marker, [StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -lt 0) {
        throw "The discovered profile is not under a preview user tree: $($profile.FullName)"
    }
    $StateRoot = $profile.FullName.Substring(0, $markerIndex)
}

$resolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
$profiles = @(Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'user') `
    -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'ForzaProfile' -and $_.Directory.Name -eq 'ForzaProfile' })
if ($profiles.Count -eq 0) {
    throw "No ForzaProfile save exists under $resolvedStateRoot\user"
}
if (@(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Pinyon Shift is already running.'
}
if ([bool]$ReplaySnapshotSignature -xor [bool]$ReplaySnapshotDir) {
    throw 'ReplaySnapshotSignature and ReplaySnapshotDir must be supplied together.'
}
if ($ReplaySnapshotDir) {
    $repositoryRoot = Split-Path $PSScriptRoot -Parent
    $localRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.local'))
    $resolvedSnapshotDir = [IO.Path]::GetFullPath($ReplaySnapshotDir)
    $localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedSnapshotDir.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "ReplaySnapshotDir must be below $localRoot"
    }
    if (Test-Path -LiteralPath $resolvedSnapshotDir) {
        throw "ReplaySnapshotDir already exists: $resolvedSnapshotDir"
    }
    if (Test-Path -LiteralPath "$resolvedSnapshotDir.partial") {
        throw "Replay snapshot staging directory already exists: $resolvedSnapshotDir.partial"
    }
    $ReplaySnapshotDir = $resolvedSnapshotDir
}

$savedCensus = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS
$savedScene = $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE
$savedIndexScan = $env:PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE
$savedTextureScan = $env:PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE
$savedReplaySnapshot = $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE
$savedReplaySnapshotDir = $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR
try {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = 'true'
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $Scene
    $env:PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE = $IndexScanSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE = $TextureScanSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE = $ReplaySnapshotSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR = $ReplaySnapshotDir
    & (Join-Path $PSScriptRoot 'launch-preview.ps1') `
        -StateRoot $resolvedStateRoot -ShaderCaptureDir $ShaderCaptureDir `
        -Json:$Json
}
finally {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = $savedCensus
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $savedScene
    $env:PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE = $savedIndexScan
    $env:PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE = $savedTextureScan
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE = $savedReplaySnapshot
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR = $savedReplaySnapshotDir
}
