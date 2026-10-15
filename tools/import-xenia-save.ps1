<#
.SYNOPSIS
Use a Forza Horizon save copied from a Xenia profile.

.DESCRIPTION
FH1 signs its saves with the signed-in profile's XUID, so a save from a Xenia
profile only loads under that same XUID (#335). Xenia keeps it in the content
folder's name: <Xenia>\content\<XUID>\4D5309C9.

This copies that 4D5309C9 folder to <state>\user\<XUID>\4D5309C9 and selects
the XUID with the user_xuid setting. The existing save stays in its own XUID
folder and is never changed; run with -Restore to switch back to it.

The work is in tools/pinyon_saves.py (`pinyon.py import-save --xenia`), the
one implementation every OS uses.

.EXAMPLE
.\tools\import-xenia-save.ps1 -StateRoot $state -Source 'C:\Xenia\content\E030000012345678\4D5309C9'
#>
[CmdletBinding(DefaultParameterSetName = 'Import')]
param(
    [Parameter(Mandatory)] [string]$StateRoot,
    [Parameter(Mandatory, ParameterSetName = 'Import')] [string]$Source,
    [Parameter(ParameterSetName = 'Import')] [string]$Xuid,
    [Parameter(Mandatory, ParameterSetName = 'Restore')] [switch]$Restore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')

$arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'import-save',
    '--state-root', [IO.Path]::GetFullPath($StateRoot), '--json')
if ($Restore) { $arguments += '--default-profile' }
else {
    $arguments += '--xenia', $Source
    if ($Xuid) { $arguments += '--xuid', $Xuid }
}
$output = @(& (Get-PinyonPython) @arguments)
$exitCode = $LASTEXITCODE
$line = @($output | Where-Object { $_ -is [string] -and $_.StartsWith('{') } | Select-Object -Last 1)
if ($exitCode -ne 0 -or $line.Count -eq 0) {
    $message = 'The save was not imported.'
    if ($line.Count) { try { $message = ($line[0] | ConvertFrom-Json).error } catch { } }
    [Console]::Error.WriteLine($message)
    exit 1
}
$line[0]
