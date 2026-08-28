[CmdletBinding()]
param(
    [string]$StateRoot,
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

$savedCensus = $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS
try {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = 'true'
    & (Join-Path $PSScriptRoot 'launch-preview.ps1') `
        -StateRoot $resolvedStateRoot -Json:$Json
}
finally {
    $env:REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS = $savedCensus
}
