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
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$IsolatedDrawSignature,
    [string]$IsolatedDrawDir,
    [switch]$RequireFreshVisibilityCandidate,
    [switch]$AutoSelectFreshVisibilityCandidate,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$PassAnchorSignature,
    [switch]$PublishRetainedPass,
    [ValidatePattern('^[0-9A-Fa-f]{16}(?:/[0-9A-Fa-f]{16}){3}$')]
    [string]$ConsumerFamily,
    [string]$ConsumerReadbackDir,
    [ValidateRange(1, 16)]
    [int]$ConsumerReadbackSamples = 1,
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
if ($AutoSelectFreshVisibilityCandidate -and $IsolatedDrawSignature) {
    throw 'AutoSelectFreshVisibilityCandidate and IsolatedDrawSignature are mutually exclusive.'
}
if ($AutoSelectFreshVisibilityCandidate -and -not $IsolatedDrawDir) {
    throw 'AutoSelectFreshVisibilityCandidate requires IsolatedDrawDir.'
}
if ($AutoSelectFreshVisibilityCandidate -and $PassAnchorSignature) {
    throw 'AutoSelectFreshVisibilityCandidate does not support PassAnchorSignature.'
}
if ($PublishRetainedPass -and
    (-not $IsolatedDrawSignature -or -not $PassAnchorSignature)) {
    throw 'PublishRetainedPass requires IsolatedDrawSignature and PassAnchorSignature.'
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

if ($IsolatedDrawDir) {
    if (-not $IsolatedDrawSignature -and -not $AutoSelectFreshVisibilityCandidate) {
        throw 'IsolatedDrawDir requires IsolatedDrawSignature or AutoSelectFreshVisibilityCandidate'
    }
    $repositoryRoot = Split-Path $PSScriptRoot -Parent
    $localRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.local'))
    $resolvedIsolatedDrawDir = [IO.Path]::GetFullPath($IsolatedDrawDir)
    $localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedIsolatedDrawDir.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "IsolatedDrawDir must be below $localRoot"
    }
    if (Test-Path -LiteralPath $resolvedIsolatedDrawDir) {
        throw "IsolatedDrawDir already exists: $resolvedIsolatedDrawDir"
    }
    if (Test-Path -LiteralPath "$resolvedIsolatedDrawDir.partial") {
        throw "Isolated draw staging directory already exists: $resolvedIsolatedDrawDir.partial"
    }
    $IsolatedDrawDir = $resolvedIsolatedDrawDir
}
if ($RequireFreshVisibilityCandidate -and
    -not $IsolatedDrawSignature -and -not $AutoSelectFreshVisibilityCandidate) {
    throw 'RequireFreshVisibilityCandidate requires IsolatedDrawSignature or AutoSelectFreshVisibilityCandidate'
}

if ($ConsumerReadbackDir) {
    if (-not $ConsumerFamily) {
        throw 'ConsumerReadbackDir requires ConsumerFamily'
    }
    $repositoryRoot = Split-Path $PSScriptRoot -Parent
    $localRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.local'))
    $resolvedConsumerReadbackDir = [IO.Path]::GetFullPath($ConsumerReadbackDir)
    $localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedConsumerReadbackDir.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "ConsumerReadbackDir must be below $localRoot"
    }
    if (Test-Path -LiteralPath $resolvedConsumerReadbackDir) {
        throw "ConsumerReadbackDir already exists: $resolvedConsumerReadbackDir"
    }
    if (Test-Path -LiteralPath "$resolvedConsumerReadbackDir.partial") {
        throw "Consumer readback staging directory already exists: $resolvedConsumerReadbackDir.partial"
    }
    $ConsumerReadbackDir = $resolvedConsumerReadbackDir
}

$savedCensus = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS
$savedScene = $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE
$savedIndexScan = $env:PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE
$savedTextureScan = $env:PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE
$savedReplaySnapshot = $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE
$savedReplaySnapshotDir = $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR
$savedIsolatedDraw = $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE
$savedIsolatedDrawDir = $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR
$savedVisibilityGate = $env:PINYON_SHIFT_NATIVE_RENDERER_REQUIRE_FRESH_VISIBILITY_CANDIDATE
$savedAutoVisibilityCandidate =
    $env:PINYON_SHIFT_NATIVE_RENDERER_AUTO_SELECT_FRESH_VISIBILITY_CANDIDATE
$savedPassAnchor = $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE
$savedPassPublication = $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS
$savedConsumerFamily = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY
$savedConsumerReadbackDir = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR
$savedConsumerReadbackSamples = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES
try {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = 'true'
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $Scene
    $env:PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE = $IndexScanSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE = $TextureScanSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE = $ReplaySnapshotSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR = $ReplaySnapshotDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE = $IsolatedDrawSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR = $IsolatedDrawDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_REQUIRE_FRESH_VISIBILITY_CANDIDATE =
        if ($RequireFreshVisibilityCandidate -or $AutoSelectFreshVisibilityCandidate) {
            'true'
        } else { $null }
    $env:PINYON_SHIFT_NATIVE_RENDERER_AUTO_SELECT_FRESH_VISIBILITY_CANDIDATE =
        if ($AutoSelectFreshVisibilityCandidate) { 'true' } else { $null }
    $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE = $PassAnchorSignature
    $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS =
        if ($PublishRetainedPass) { 'true' } else { $null }
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY = $ConsumerFamily
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR = $ConsumerReadbackDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES =
        if ($ConsumerReadbackDir) { [string]$ConsumerReadbackSamples } else { $null }
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
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE = $savedIsolatedDraw
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR = $savedIsolatedDrawDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_REQUIRE_FRESH_VISIBILITY_CANDIDATE =
        $savedVisibilityGate
    $env:PINYON_SHIFT_NATIVE_RENDERER_AUTO_SELECT_FRESH_VISIBILITY_CANDIDATE =
        $savedAutoVisibilityCandidate
    $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE = $savedPassAnchor
    $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS = $savedPassPublication
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY = $savedConsumerFamily
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR = $savedConsumerReadbackDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES =
        $savedConsumerReadbackSamples
}
