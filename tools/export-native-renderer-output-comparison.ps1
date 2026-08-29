[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Capture,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
    [Parameter(Mandatory)]
    [string]$OutputDir,
    [string]$CompositionMarker =
        'PinyonShift NR-04C native display composition',
    [string]$SelectionMarker =
        'PinyonShift NR-04C native output selection'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.local'))
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
$resolvedCapture = (Resolve-Path -LiteralPath $Capture).Path
$resolvedOutputDir = [IO.Path]::GetFullPath($OutputDir)
if (-not $resolvedCapture.StartsWith(
        $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Capture must be below $localRoot"
}
if (-not $resolvedOutputDir.StartsWith(
        $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDir must be below $localRoot"
}
if (Test-Path -LiteralPath $resolvedOutputDir) {
    throw "OutputDir already exists: $resolvedOutputDir"
}

$qrenderdoc = Join-Path ([IO.Path]::GetFullPath($RenderDocRoot)) 'qrenderdoc.exe'
if (-not (Test-Path -LiteralPath $qrenderdoc -PathType Leaf)) {
    throw "qrenderdoc.exe was not found below RenderDocRoot: $RenderDocRoot"
}
$signature = Get-AuthenticodeSignature -LiteralPath $qrenderdoc
if ([string]$signature.Status -ne 'Valid') {
    throw 'qrenderdoc.exe does not have a valid Authenticode signature'
}

$script = Join-Path $PSScriptRoot `
    'export-native-renderer-output-comparison.py'
[void](New-Item -ItemType Directory -Path $resolvedOutputDir)
$savedCapture = $env:PINYON_SHIFT_RENDERDOC_CAPTURE
$savedOutput = $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR
$savedCompositionMarker = $env:PINYON_SHIFT_RENDERDOC_COMPOSITION_MARKER
$savedSelectionMarker = $env:PINYON_SHIFT_RENDERDOC_SELECTION_MARKER
try {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $resolvedCapture
    $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR = $resolvedOutputDir
    $env:PINYON_SHIFT_RENDERDOC_COMPOSITION_MARKER = $CompositionMarker
    $env:PINYON_SHIFT_RENDERDOC_SELECTION_MARKER = $SelectionMarker
    $process = Start-Process -FilePath $qrenderdoc `
        -ArgumentList @('--python', $script) -PassThru -Wait `
        -WindowStyle Hidden
    if ($process.ExitCode) {
        throw "qrenderdoc export exited with code $($process.ExitCode)"
    }
}
finally {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $savedCapture
    $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR = $savedOutput
    $env:PINYON_SHIFT_RENDERDOC_COMPOSITION_MARKER =
        $savedCompositionMarker
    $env:PINYON_SHIFT_RENDERDOC_SELECTION_MARKER = $savedSelectionMarker
}

$report = Join-Path $resolvedOutputDir 'native-output-comparison.json'
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'qrenderdoc exited without producing the comparison report.'
}
Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
