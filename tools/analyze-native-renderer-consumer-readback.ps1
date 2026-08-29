[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ReadbackRoot,
    [Parameter(Mandatory)]
    [string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.local'))
$localPrefix = $localRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
$resolvedReadbackRoot = [IO.Path]::GetFullPath($ReadbackRoot)
$resolvedOutputDir = [IO.Path]::GetFullPath($OutputDir)
foreach ($path in @($resolvedReadbackRoot, $resolvedOutputDir)) {
    if (-not $path.StartsWith($localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Consumer evidence paths must remain below $localRoot"
    }
}
if (-not (Test-Path -LiteralPath $resolvedReadbackRoot -PathType Container)) {
    throw "ReadbackRoot does not exist: $resolvedReadbackRoot"
}
if (Test-Path -LiteralPath $resolvedOutputDir) {
    throw "OutputDir already exists: $resolvedOutputDir"
}

python (Join-Path $PSScriptRoot 'analyze-native-renderer-consumer-readback.py') `
    $resolvedReadbackRoot $resolvedOutputDir
if ($LASTEXITCODE) {
    throw "Consumer readback analysis exited with code $LASTEXITCODE"
}
