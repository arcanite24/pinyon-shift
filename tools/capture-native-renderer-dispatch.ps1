[CmdletBinding()]
param(
    [string]$StateRoot,
    [string]$StaticOutput,
    [ValidatePattern('^[a-z_]{1,32}$')]
    [string]$Scene = 'unmarked',
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path $PSScriptRoot -Parent
if (-not $StateRoot) {
    $sourceRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source'
    $profile = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq 'ForzaProfile' -and
            $_.Directory.Name -eq 'ForzaProfile'
        } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $profile) {
        throw "No installed preview ForzaProfile was found under $sourceRoot"
    }
    $separator = [IO.Path]::DirectorySeparatorChar
    $marker = "${separator}user${separator}"
    $markerIndex = $profile.FullName.IndexOf(
        $marker, [StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -lt 0) {
        throw "The discovered profile is not under a preview user tree: $($profile.FullName)"
    }
    $StateRoot = $profile.FullName.Substring(0, $markerIndex)
}

$resolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
$profiles = @(Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'user') `
    -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'ForzaProfile' -and
        $_.Directory.Name -eq 'ForzaProfile'
    })
if ($profiles.Count -eq 0) {
    throw "No ForzaProfile save exists under $resolvedStateRoot\user"
}
if (@(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Pinyon Shift is already running.'
}

if ($StaticOutput) {
    $localRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.local'))
    $resolvedStaticOutput = [IO.Path]::GetFullPath($StaticOutput)
    $localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedStaticOutput.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "StaticOutput must be below $localRoot"
    }
    $generatedRoot = Join-Path $repositoryRoot '.local\generated\default'
    $imagePath = Join-Path $repositoryRoot '.local\analysis\default-image.bin'
    if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) {
        throw "Static dispatch discovery image is missing: $imagePath"
    }
    & python (Join-Path $PSScriptRoot 'discover-native-renderer-dispatch.py') `
        $generatedRoot --image $imagePath --output $resolvedStaticOutput
    if ($LASTEXITCODE -ne 0) {
        throw 'Static dispatch discovery failed.'
    }
}

$savedDiscovery = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY
$savedCensus = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS
$savedScene = $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE
try {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY = 'true'
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = 'true'
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $Scene
    & (Join-Path $PSScriptRoot 'launch-preview.ps1') `
        -StateRoot $resolvedStateRoot -Json:$Json
}
finally {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY = $savedDiscovery
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = $savedCensus
    $env:PINYON_SHIFT_NATIVE_RENDERER_SCENE = $savedScene
}
