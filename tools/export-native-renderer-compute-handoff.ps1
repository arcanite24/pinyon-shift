[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Capture,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$ResourceName,
    [Parameter(Mandatory)]
    [string]$Output
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot '.local'))
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
$resolvedCapture = (Resolve-Path -LiteralPath $Capture).Path
$resolvedOutput = [IO.Path]::GetFullPath($Output)
foreach ($item in @(
        @{ Name = 'Capture'; Value = $resolvedCapture },
        @{ Name = 'Output'; Value = $resolvedOutput }
    )) {
    if (-not $item.Value.StartsWith(
            $localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$($item.Name) must be below $localRoot"
    }
}
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "Output already exists: $resolvedOutput"
}

$qrenderdoc = Join-Path ([IO.Path]::GetFullPath($RenderDocRoot)) 'qrenderdoc.exe'
if (-not (Test-Path -LiteralPath $qrenderdoc -PathType Leaf)) {
    throw "qrenderdoc.exe was not found below RenderDocRoot: $RenderDocRoot"
}
$signature = Get-AuthenticodeSignature -LiteralPath $qrenderdoc
if ([string]$signature.Status -ne 'Valid') {
    throw 'qrenderdoc.exe does not have a valid Authenticode signature'
}

$script = Join-Path $PSScriptRoot 'export-native-renderer-compute-handoff.py'
$parent = Split-Path $resolvedOutput -Parent
[void](New-Item -ItemType Directory -Path $parent -Force)
$savedCapture = $env:PINYON_SHIFT_RENDERDOC_CAPTURE
$savedResource = $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME
$savedOutput = $env:PINYON_SHIFT_RENDERDOC_COMPUTE_HANDOFF
try {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $resolvedCapture
    $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME = $ResourceName
    $env:PINYON_SHIFT_RENDERDOC_COMPUTE_HANDOFF = $resolvedOutput
    $process = Start-Process -FilePath $qrenderdoc `
        -ArgumentList @('--python', $script) -PassThru -Wait
    if ($process.ExitCode) {
        throw "qrenderdoc compute handoff export exited with code $($process.ExitCode)"
    }
}
finally {
    $env:PINYON_SHIFT_RENDERDOC_CAPTURE = $savedCapture
    $env:PINYON_SHIFT_RENDERDOC_RESOURCE_NAME = $savedResource
    $env:PINYON_SHIFT_RENDERDOC_COMPUTE_HANDOFF = $savedOutput
}
if (-not (Test-Path -LiteralPath $resolvedOutput -PathType Leaf)) {
    throw 'qrenderdoc exited without producing the compute handoff report.'
}
Get-Content -LiteralPath $resolvedOutput -Raw | ConvertFrom-Json
