[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('status', 'install', 'enable', 'disable', 'remove')] [string]$Action,
    [Parameter(Mandatory)] [string]$StateRoot,
    # install: the player's XE 1.0 download and, optionally, the 1.01 hotfix.
    [Parameter(ValueFromRemainingArguments)] [string[]]$Archives = @()
)

# Launcher support for the Forza Horizon XE mod (tools/pinyon_xe.py). Prints
# one JSON object; a failure prints {"result": "error", ...} and exits 1.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')
$arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'xe', $Action)
if ($Action -eq 'install') {
    if ($Archives.Count -eq 0) { throw 'Choose the XE 1.0 download and, if you have it, the 1.01 hotfix.' }
    $arguments += $Archives
    $arguments += '--replace'
}
$arguments += '--state-root', ([IO.Path]::GetFullPath($StateRoot)), '--json'
& (Get-PinyonPython) @arguments
exit $LASTEXITCODE
