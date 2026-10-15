[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('status', 'import', 'enable', 'disable', 'restore', 'club-on', 'club-off')] [string]$Action,
    [Parameter(Mandatory)] [string]$StateRoot,
    # import: the player's title-update package, folder or ZIP.
    [string]$InputPath
)

# Launcher support for the optional FH1 v4 title update (TITLE_UPDATE_V4_BACKLOG
# TU-2). The base build stays the default; enabling only records the choice in
# <state>/config/title-update.json, and the launcher builds and runs v4 with
# tools/build-v4.ps1 and launch-preview.ps1 -TitleUpdateV4. The work is in
# tools/pinyon_title_update.py (`pinyon.py title-update`), the one
# implementation every OS uses. Prints one JSON status object; a failure writes
# its reason to standard error and exits 1.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')

if ($Action -eq 'import' -and -not $InputPath) { throw 'Choose the title-update package, folder or ZIP.' }
$Action = $Action.ToLowerInvariant()
$arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'title-update', $Action)
if ($Action -eq 'import') { $arguments += $InputPath }
$arguments += '--state-root', ([IO.Path]::GetFullPath($StateRoot)), '--json'
$output = @(& (Get-PinyonPython) @arguments)
$exitCode = $LASTEXITCODE
$line = @($output | Where-Object { $_ -is [string] -and $_.StartsWith('{') } | Select-Object -Last 1)
if ($exitCode -ne 0 -or $line.Count -eq 0) {
    $message = 'Title-update management stopped.'
    if ($line.Count) { try { $message = ($line[0] | ConvertFrom-Json).error } catch { } }
    [Console]::Error.WriteLine($message)
    exit 1
}
$line[0]
