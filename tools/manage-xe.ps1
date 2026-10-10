[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('status', 'install', 'download', 'enable', 'disable', 'remove')] [string]$Action,
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
# download: open both ModDB pages in the player's browser, then install the
# archives from Downloads once both finish (ModDB disallows automated
# downloads, so the browser fetches them; #426).
if ($Action -eq 'download') {
    $arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'xe', 'install', '--find', '--open-pages',
        '--wait', '14400', '--replace')
}
$arguments += '--state-root', ([IO.Path]::GetFullPath($StateRoot)), '--json'
& (Get-PinyonPython) @arguments
exit $LASTEXITCODE
