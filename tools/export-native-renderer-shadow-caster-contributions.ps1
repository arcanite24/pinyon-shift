[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Capture,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
    [Parameter(Mandatory)]
    [string]$Lineage,
    [Parameter(Mandatory)]
    [ValidateRange(1, 1024)]
    [int]$EpochOrdinal,
    [Parameter(Mandatory)]
    [string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.local'))
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
$resolvedCapture = (Resolve-Path -LiteralPath $Capture).Path
$resolvedLineage = (Resolve-Path -LiteralPath $Lineage).Path
$resolvedOutputDir = [IO.Path]::GetFullPath($OutputDir)
foreach ($item in @(
        @{ Name = 'Capture'; Value = $resolvedCapture },
        @{ Name = 'Lineage'; Value = $resolvedLineage },
        @{ Name = 'OutputDir'; Value = $resolvedOutputDir }
    )) {
    if (-not $item.Value.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$($item.Name) must be below $localRoot"
    }
}
if (Test-Path -LiteralPath $resolvedOutputDir) {
    throw "OutputDir already exists: $resolvedOutputDir"
}

$lineageDocument = Get-Content -LiteralPath $resolvedLineage -Raw |
    ConvertFrom-Json
if ([string]$lineageDocument.schema -ne
    'pinyon-shift.native-renderer-effect-resource-lineage.v1') {
    throw 'Lineage has an unsupported schema.'
}
$captureHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedCapture).Hash
if ([string]$lineageDocument.capture.sha256 -ne $captureHash) {
    throw 'Capture and lineage hashes differ.'
}
$epoch = @($lineageDocument.epochs) |
    Where-Object { [int]$_.ordinal -eq $EpochOrdinal }
if ($epoch.Count -ne 1) {
    throw "EpochOrdinal matched $($epoch.Count) lineage epochs."
}
$eventIds = @($epoch[0].depth_write_events)
if (-not $eventIds.Count -or $eventIds.Count -gt 128) {
    throw 'Selected epoch must contain 1 through 128 depth writes.'
}
for ($index = 0; $index -lt $eventIds.Count; $index++) {
    $eventId = [int]$eventIds[$index]
    if ($eventId -le 0 -or
        ($index -and $eventId -le [int]$eventIds[$index - 1])) {
        throw 'Selected epoch depth writes must be positive and ordered.'
    }
}
$resourceName = [string]$lineageDocument.resource.resource_name
if (-not $resourceName.Trim()) {
    throw 'Lineage resource name is empty.'
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
    'export-native-renderer-shadow-caster-contributions.py'
[void](New-Item -ItemType Directory -Path $resolvedOutputDir)
$savedCapture = $env:PINYON_SHIFT_RENDERDOC_CAPTURE
$savedOutput = $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR
$savedResourceName = $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME
$savedEventIds = $env:PINYON_SHIFT_RENDERDOC_EVENT_IDS
try {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $resolvedCapture
    $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR = $resolvedOutputDir
    $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME = $resourceName
    $env:PINYON_SHIFT_RENDERDOC_EVENT_IDS = $eventIds -join ','
    $process = Start-Process -FilePath $qrenderdoc `
        -ArgumentList @('--python', $script) -PassThru -Wait
    if ($process.ExitCode) {
        throw "qrenderdoc contribution export exited with code $($process.ExitCode)"
    }
}
finally {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $savedCapture
    $env:PINYON_SHIFT_RENDERDOC_EXPORT_DIR = $savedOutput
    $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME = $savedResourceName
    $env:PINYON_SHIFT_RENDERDOC_EVENT_IDS = $savedEventIds
}

$report = Join-Path $resolvedOutputDir 'shadow-caster-contributions.json'
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
    throw 'qrenderdoc exited without producing the contribution report.'
}
Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
