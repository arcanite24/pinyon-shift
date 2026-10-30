[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('list', 'enable', 'disable', 'move', 'option', 'install', 'remove')]
    [string]$Action,
    [Parameter(Mandatory)] [string]$StateRoot,
    # enable, disable, move, option and remove: the mod's folder name.
    [string]$Name = '',
    # move: up or down. option: KEY=VALUE. install: replace to overwrite an installed mod.
    [string]$Value = '',
    # install: a ZIP or a folder.
    [string]$Path = ''
)

# Launcher support for the mod manager (tools/pinyon_mods.py, FB-9.1).
# Prints one JSON object; a failure prints {"result": "error", ...} and
# exits 1.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')
$arguments = @((Join-Path $PSScriptRoot 'pinyon.py'), 'mods', $Action)
switch ($Action) {
    'move' { $arguments += $Name, $Value }
    'option' { $key, $choice = $Value -split '=', 2; $arguments += $Name, $key, $choice }
    'install' { $arguments += $Path; if ($Value -eq 'replace') { $arguments += '--replace' } }
    'list' { }
    default { $arguments += $Name }
}
$arguments += '--state-root', ([IO.Path]::GetFullPath($StateRoot)), '--json'
& (Get-PinyonPython) @arguments
exit $LASTEXITCODE
