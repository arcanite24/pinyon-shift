[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)] [ValidateSet('list', 'import', 'enable', 'disable', 'udlc')] [string]$Action,
    [Parameter(Mandatory)] [string]$StateRoot,
    [string]$InputPath,
    [string]$PackageId,
    [switch]$Find,
    [switch]$OpenPages,
    [int]$Wait = 0,
    [switch]$Traffic,
    [Parameter(ValueFromRemainingArguments)] [string[]]$Archives = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')
$arguments = @((Join-Path $PSScriptRoot 'manage-fh1-dlc.py'), $Action, '--state-root', $StateRoot)
if ($InputPath) { $arguments += @('--source', $InputPath) }
if ($PackageId) { $arguments += @('--package-id', $PackageId) }
if ($Action -eq 'udlc') {
    $arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'dlc', 'udlc') + $Archives
    if ($Find) { $arguments += '--find' }
    if ($OpenPages) { $arguments += '--open-pages' }
    if ($Wait) { $arguments += @('--wait', "$Wait") }
    if ($Traffic) { $arguments += '--traffic' }
    $arguments += @('--state-root', $StateRoot, '--json')
}
& (Get-PinyonPython) @arguments
# manage-fh1-dlc.py has written the reason to stderr; the launcher shows it
# as it is, without a PowerShell error record around it (#573).
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
