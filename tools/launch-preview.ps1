[CmdletBinding()]
param(
    [ValidateSet('Release')]
    [string]$Configuration = 'Release',
    [string]$GameRoot,
    [string]$StateRoot
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

foreach ($directory in @('', 'cache', 'config', 'crashes', 'logs', 'update', 'user')) {
    $path = if ($directory) { Join-Path $resolvedStateRoot $directory } else { $resolvedStateRoot }
    [void](New-Item -ItemType Directory -Force -Path $path)
}

$savedStateRoot = $env:PINYON_SHIFT_STATE_ROOT
$savedGameRoot = $env:PINYON_SHIFT_GAME_ROOT
$savedTearing = $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING
try {
    $env:PINYON_SHIFT_STATE_ROOT = $resolvedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $resolvedGameRoot
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = 'false'
    Start-Process -FilePath $executable -WorkingDirectory (Split-Path $executable -Parent)
}
finally {
    $env:PINYON_SHIFT_STATE_ROOT = $savedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $savedGameRoot
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = $savedTearing
}
