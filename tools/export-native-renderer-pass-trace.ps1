[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Capture,
    [Parameter(Mandatory)]
    [string]$RenderDocRoot,
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

$script = Join-Path $PSScriptRoot 'export-native-renderer-pass-trace.py'
$parent = Split-Path $resolvedOutput -Parent
[void](New-Item -ItemType Directory -Path $parent -Force)
$wrapper = Join-Path $parent ("pass-trace-" + [guid]::NewGuid().ToString('N') + '.py')
$process = $null
try {
    @(
        'import os'
        'import runpy'
        'os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"] = ' + (ConvertTo-Json -Compress $resolvedCapture)
        'os.environ["PINYON_SHIFT_RENDERDOC_PASS_TRACE"] = ' + (ConvertTo-Json -Compress $resolvedOutput)
        'runpy.run_path(' + (ConvertTo-Json -Compress $script) + ', run_name="__main__")'
    ) | Set-Content -LiteralPath $wrapper -Encoding utf8
    $relativeWrapper = [IO.Path]::GetRelativePath($repoRoot, $wrapper).Replace('\', '/')
    $process = Start-Process -FilePath $qrenderdoc `
        -ArgumentList @('--python', $relativeWrapper) `
        -WorkingDirectory $repoRoot -PassThru
    $deadline = [DateTime]::UtcNow.AddMinutes(15)
    while (-not (Test-Path -LiteralPath $resolvedOutput -PathType Leaf) -and
           -not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }
    if (-not (Test-Path -LiteralPath $resolvedOutput -PathType Leaf)) {
        throw "qrenderdoc exited or timed out without producing the pass trace."
    }
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $wrapper -ErrorAction SilentlyContinue
}
if (-not (Test-Path -LiteralPath $resolvedOutput -PathType Leaf)) {
    throw 'qrenderdoc exited without producing the pass trace.'
}
Get-Content -LiteralPath $resolvedOutput -Raw | ConvertFrom-Json
