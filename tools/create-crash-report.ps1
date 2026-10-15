[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$StateRoot,
    [Parameter(Mandatory)] [string]$Executable,
    [Parameter(Mandatory)] [datetime]$StartedUtc,
    [Parameter(Mandatory)] [int64]$ProcessId,
    [Parameter(Mandatory)] [int64]$ExitCode,
    [string]$RepositoryUrl = 'https://github.com/arcanite24/pinyon-shift',
    [switch]$Json
)

# Bundles a crash for an issue report: a sanitized ZIP in <state>/reports and
# a prefilled GitHub issue link. The work is in tools/pinyon_crash.py
# (`pinyon.py crash-report create`), the one implementation every OS uses
# (LX-3.5); see it for what the bundle holds and how paths and the user name
# are replaced. Prints the pending-report record: crash_id, bundle, issue_url.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')

$arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'crash-report', 'create',
    '--state-root', [IO.Path]::GetFullPath($StateRoot),
    '--executable', (Resolve-Path -LiteralPath $Executable).Path,
    '--started-utc', $StartedUtc.ToUniversalTime().ToString('o'),
    '--process-id', [string]$ProcessId, '--exit-code', [string]$ExitCode,
    '--repository-url', $RepositoryUrl, '--json')
$output = @(& (Get-PinyonPython) @arguments)
$exitCode = $LASTEXITCODE
$line = @($output | Where-Object { $_ -is [string] -and $_.StartsWith('{') } | Select-Object -Last 1)
if ($exitCode -ne 0 -or $line.Count -eq 0) {
    $message = 'The crash report could not be prepared.'
    if ($line.Count) { try { $message = ($line[0] | ConvertFrom-Json).error } catch { } }
    throw $message
}
if ($Json) { $line[0] } else { $line[0] | ConvertFrom-Json }
