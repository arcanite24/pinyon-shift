[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$StateRoot,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$IsolatedDrawSignature,
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$PassAnchorSignature,
    [switch]$PublishRetainedPass,
    [ValidatePattern('^[0-9A-Fa-f]{16}(?:/[0-9A-Fa-f]{16}){3}$')]
    [string]$ConsumerFamily,
    [string]$ConsumerReadbackDir,
    [ValidateRange(1, 16)]
    [int]$ConsumerReadbackSamples = 1,
    [string]$IsolatedDrawDir,
    [Parameter(Mandatory)]
    [string]$CaptureDir,
    [ValidateSet('open_world_day', 'open_world_night', 'garage', 'race')]
    [string]$Scene = 'open_world_day'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.local'))
$resolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
$resolvedCaptureDir = [IO.Path]::GetFullPath($CaptureDir)
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
if (-not $resolvedCaptureDir.StartsWith(
        $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "CaptureDir must be below $localRoot"
}
if (Test-Path -LiteralPath $resolvedCaptureDir) {
    throw "CaptureDir already exists: $resolvedCaptureDir"
}
if ([bool]$PassAnchorSignature -xor [bool]$IsolatedDrawDir) {
    throw 'PassAnchorSignature and IsolatedDrawDir must be supplied together.'
}
if ($PublishRetainedPass -and -not $PassAnchorSignature) {
    throw 'PublishRetainedPass requires PassAnchorSignature.'
}
if ($IsolatedDrawDir) {
    $resolvedIsolatedDrawDir = [IO.Path]::GetFullPath($IsolatedDrawDir)
    if (-not $resolvedIsolatedDrawDir.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "IsolatedDrawDir must be below $localRoot"
    }
    if (Test-Path -LiteralPath $resolvedIsolatedDrawDir) {
        throw "IsolatedDrawDir already exists: $resolvedIsolatedDrawDir"
    }
    $IsolatedDrawDir = $resolvedIsolatedDrawDir
}
if ($ConsumerReadbackDir) {
    if (-not $ConsumerFamily) {
        throw 'ConsumerReadbackDir requires ConsumerFamily'
    }
    $resolvedConsumerReadbackDir = [IO.Path]::GetFullPath($ConsumerReadbackDir)
    if (-not $resolvedConsumerReadbackDir.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "ConsumerReadbackDir must be below $localRoot"
    }
    if (Test-Path -LiteralPath $resolvedConsumerReadbackDir) {
        throw "ConsumerReadbackDir already exists: $resolvedConsumerReadbackDir"
    }
    $ConsumerReadbackDir = $resolvedConsumerReadbackDir
}

$profile = Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'user') `
    -Recurse -File -Filter ForzaProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match 'ForzaProfile\\ForzaProfile$' } |
    Select-Object -First 1
if (-not $profile) {
    throw "StateRoot does not contain an AppData ForzaProfile: $resolvedStateRoot"
}
if (@(Get-Process -Name pinyon_shift -ErrorAction SilentlyContinue).Count) {
    throw 'Pinyon Shift is already running.'
}

$renderdoc = Join-Path ([IO.Path]::GetFullPath($RenderDocRoot)) 'renderdoccmd.exe'
if (-not (Test-Path -LiteralPath $renderdoc -PathType Leaf)) {
    throw "renderdoccmd.exe was not found below RenderDocRoot: $RenderDocRoot"
}
$signature = Get-AuthenticodeSignature -LiteralPath $renderdoc
if ([string]$signature.Status -ne 'Valid') {
    throw "renderdoccmd.exe does not have a valid Authenticode signature"
}

$executable = Join-Path $repoRoot 'out\build\win-amd64-release\pinyon_shift.exe'
$gameRoot = (Resolve-Path (Join-Path $repoRoot '.local\game\base')).Path
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'The preview has not been built.'
}
[void](New-Item -ItemType Directory -Path $resolvedCaptureDir)

$saved = @{
    state = $env:PINYON_SHIFT_STATE_ROOT
    game = $env:PINYON_SHIFT_GAME_ROOT
    tearing = $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING
    census = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS
    scene = $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE
    draw = $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE
    draw_dir = $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR
    pass_anchor = $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE
    pass_publication = $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS
    consumer_family = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY
    consumer_readback_dir = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR
    consumer_readback_samples = $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES
}
try {
    $env:PINYON_SHIFT_STATE_ROOT = $resolvedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $gameRoot
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = 'false'
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = 'true'
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $Scene
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE =
        if ($IsolatedDrawSignature) {
            $IsolatedDrawSignature.ToUpperInvariant()
        } else {
            $null
        }
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR = $IsolatedDrawDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE =
        if ($PassAnchorSignature) {
            $PassAnchorSignature.ToUpperInvariant()
        } else {
            $null
        }
    $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS =
        if ($PublishRetainedPass) { 'true' } else { $null }
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY = $ConsumerFamily
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR = $ConsumerReadbackDir
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES =
        if ($ConsumerReadbackDir) { [string]$ConsumerReadbackSamples } else { $null }
    & $renderdoc capture -w `
        -d (Split-Path $executable -Parent) `
        -c (Join-Path $resolvedCaptureDir 'reference') `
        $executable
    if ($LASTEXITCODE) {
        throw "RenderDoc capture exited with code $LASTEXITCODE"
    }
}
finally {
    $env:PINYON_SHIFT_STATE_ROOT = $saved.state
    $env:PINYON_SHIFT_GAME_ROOT = $saved.game
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = $saved.tearing
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = $saved.census
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $saved.scene
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE = $saved.draw
    $env:PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR = $saved.draw_dir
    $env:PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE = $saved.pass_anchor
    $env:PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS = $saved.pass_publication
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY = $saved.consumer_family
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR =
        $saved.consumer_readback_dir
    $env:PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES =
        $saved.consumer_readback_samples
}

$captures = @(Get-ChildItem -LiteralPath $resolvedCaptureDir -File -Filter '*.rdc')
if (-not $captures.Count) {
    throw 'RenderDoc exited without producing an RDC capture.'
}
$captures
