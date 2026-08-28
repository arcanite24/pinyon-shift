[CmdletBinding()]
param(
    [string]$StateRoot,
    [string]$OutputRoot,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$resolvedStateRoot = if ($StateRoot) {
    [IO.Path]::GetFullPath($StateRoot)
} else {
    Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
}
$captureRoot = if ($OutputRoot) {
    [IO.Path]::GetFullPath($OutputRoot)
} else {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    Join-Path $repoRoot ".local\native-renderer\captures\$stamp"
}

$profile = Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'user') `
    -Filter 'ForzaProfile' -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq 'ForzaProfile' } |
    Select-Object -First 1
if ($null -eq $profile) {
    throw "The selected state root has no ForzaProfile save: $resolvedStateRoot"
}
if (@(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Pinyon Shift is already running.'
}
$localRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.local'))
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($captureRoot -ne $localRoot -and
    -not $captureRoot.StartsWith($localPrefix,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Shader capture output must remain under the repository .local directory.'
}

[void](New-Item -ItemType Directory -Force -Path $captureRoot)
$result = [ordered]@{
    capture_root = $captureRoot
    manifest = Join-Path $captureRoot 'shader-manifest.json'
    state_root = $resolvedStateRoot
    save_verified = $true
}
if ($Json) {
    $result | ConvertTo-Json -Compress
} else {
    $result
}

& (Join-Path $PSScriptRoot 'launch-preview.ps1') `
    -StateRoot $resolvedStateRoot -ShaderCaptureDir $captureRoot
