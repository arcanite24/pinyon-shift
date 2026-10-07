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
. (Join-Path $PSScriptRoot 'host-config.ps1')

$TitleId = '4D5309C9'
$DefaultXuid = 'B13EBABEBABEBABE'

function Test-Xuid([string]$Value) {
    if ($Value -notmatch '^[0-9A-Fa-f]{16}$') { return $false }
    $number = [UInt64]::Parse($Value, [Globalization.NumberStyles]::HexNumber)
    # Titles refuse XUIDs with these bits; the runtime falls back to its default.
    $number -ne 0 -and ($number -band 0x00C0000000000000) -eq 0
}

# Tests run beside unrelated game processes and set this to skip the check.
if (-not $env:PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME -and
        (Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue)) {
    throw 'Close Pinyon Shift before changing saves.'
}
$state = (Resolve-Path -LiteralPath $StateRoot).Path
$configPath = Join-Path $state 'config\pinyon_shift.toml'
$config = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }

if ($Restore) {
    $backup = New-HostConfigBackup $configPath
    Write-HostConfig $configPath (Set-TomlValue $config 'user_xuid' "`"$DefaultXuid`"")
    [pscustomobject]@{ xuid = $DefaultXuid; config_backup = $backup } | ConvertTo-Json
    return
}

$sourcePath = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\', '/')
$title = if ((Split-Path -Leaf $sourcePath) -ieq $TitleId) { $sourcePath } else { Join-Path $sourcePath $TitleId }
if (-not (Test-Path -LiteralPath (Join-Path $title '00000001\ForzaProfile\ForzaProfile') -PathType Leaf)) {
    throw "No Forza Horizon save found. Choose the Xenia folder content\<XUID>\$TitleId."
}
if (-not $Xuid) {
    # The folder that holds 4D5309C9 is named after the profile's XUID.
    $Xuid = Split-Path -Leaf (Split-Path -Parent $title)
    if (-not (Test-Xuid $Xuid)) {
        throw "Could not find the profile XUID in the path. Pass -Xuid with the 16-digit name of the folder above $TitleId."
    }
}
if (-not (Test-Xuid $Xuid)) { throw "'$Xuid' is not a usable 16-digit profile XUID." }
$Xuid = $Xuid.ToUpperInvariant()

$destination = Join-Path $state "user\$Xuid\$TitleId"
if (Test-Path -LiteralPath $destination) {
    throw "A save for profile $Xuid already exists at $destination; it was left unchanged."
}
$staging = "$destination.import-$([Guid]::NewGuid().ToString('N'))"
try {
    [void](New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination))
    Copy-Item -LiteralPath $title -Destination $staging -Recurse
    Move-Item -LiteralPath $staging -Destination $destination
}
finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
}

$backup = New-HostConfigBackup $configPath
Write-HostConfig $configPath (Set-TomlValue $config 'user_xuid' "`"$Xuid`"")
[pscustomobject]@{
    xuid = $Xuid
    save = $destination
    config_backup = $backup
    previous_save_kept = $true
} | ConvertTo-Json
