[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$StateRoot,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$IsolatedDrawSignature,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{16}$')]
    [string]$PassAnchorSignature,
    [Parameter(Mandatory)]
    [string]$IsolatedDrawDir,
    [Parameter(Mandatory)]
    [string]$CaptureDir,
    [ValidateSet('native', 'xenos')]
    [string]$SelectedOutput = 'native',
    [ValidateSet('open_world_day', 'open_world_night', 'garage', 'race')]
    [string]$Scene = 'open_world_day'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$settingsTool = Join-Path $PSScriptRoot 'set-graphics-experiment.ps1'
$captureTool = Join-Path $PSScriptRoot `
    'capture-native-renderer-renderdoc.ps1'
$before = & $settingsTool -Action Get -StateRoot $StateRoot -Json |
    ConvertFrom-Json
$originalRenderer = [string]$before.settings.native_renderer
$comparisonRenderer = if ($SelectedOutput -eq 'native') {
    'comparison_native'
} else {
    'comparison_xenos'
}

try {
    [void](& $settingsTool -Action SetRenderer -StateRoot $StateRoot `
        -NativeRenderer $comparisonRenderer -Json)
    & $captureTool -StateRoot $StateRoot -RenderDocRoot $RenderDocRoot `
        -IsolatedDrawSignature $IsolatedDrawSignature `
        -PassAnchorSignature $PassAnchorSignature `
        -IsolatedDrawDir $IsolatedDrawDir -CaptureDir $CaptureDir `
        -Scene $Scene
}
finally {
    [void](& $settingsTool -Action SetRenderer -StateRoot $StateRoot `
        -NativeRenderer $originalRenderer -Json)
}
