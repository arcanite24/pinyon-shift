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
# tools/build-v4.ps1 and launch-preview.ps1 -TitleUpdateV4. Prints one JSON
# status object.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$state = [IO.Path]::GetFullPath($StateRoot)
$python = Get-PinyonPython
$choice = Join-Path $state 'config/title-update.json'
$update = Join-Path $state 'title-update-v4'
$files = 'default.xexp', 'SpeechFacade_default.xexp', 'XMediaFacade_default.xexp', 'media.zip'

function Read-Choice {
    # use: run v4; club: offline 1000 Club (launch-preview.ps1 reads it).
    $result = @{ use = $false; club = $false }
    if (Test-Path -LiteralPath $choice -PathType Leaf) {
        $saved = Get-Content -LiteralPath $choice -Raw | ConvertFrom-Json
        foreach ($name in 'use', 'club') {
            if ($saved.PSObject.Properties[$name]) { $result[$name] = [bool]$saved.$name }
        }
    }
    $result
}

function Get-Status {
    $installed = @($files | Where-Object { Test-Path -LiteralPath (Join-Path $update $_) -PathType Leaf }).Count -eq $files.Count
    $saved = Read-Choice
    $use = $saved.use
    $profiles = & $python (Join-Path $PSScriptRoot 'title-update-profile.py') status --state-root $state | ConvertFrom-Json
    [ordered]@{
        installed = $installed
        use = $use -and $installed
        club = $saved.club
        built = Test-Path -LiteralPath (Join-Path $root 'out/build/win-amd64-v4/pinyon_shift.exe') -PathType Leaf
        profiles = $profiles.profiles
        pre_v4_backups = @($profiles.pre_v4_backups)
    }
}

function Set-Choice([string]$Name, [bool]$Value) {
    [void](New-Item -ItemType Directory -Force -Path (Split-Path $choice))
    $saved = Read-Choice
    $saved[$Name] = $Value
    $temporary = "$choice.tmp"
    ($saved | ConvertTo-Json) | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $choice -Force
}

switch ($Action) {
    'import' {
        if (-not $InputPath) { throw 'Choose the title-update package, folder or ZIP.' }
        $source = $InputPath
        if ($InputPath -like '*.zip') {
            $source = Join-Path ([IO.Path]::GetTempPath()) ('pinyon-tu-' + [guid]::NewGuid())
            Expand-Archive -LiteralPath $InputPath -DestinationPath $source
        }
        try {
            $result = & $python (Join-Path $PSScriptRoot 'verify-fh1-title-update.py') $source --install $state
            if ($LASTEXITCODE -ne 0) {
                $message = ($result -join "`n" | ConvertFrom-Json).error
                if (-not $message) { $message = 'it does not apply to this disc' }
                throw "The title update was not installed: $message"
            }
        } finally {
            if ($source -ne $InputPath) { Remove-Item -LiteralPath $source -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
    'enable' {
        if (-not (Get-Status).installed) { throw 'Import the verified title update first.' }
        Set-Choice 'use' $true
    }
    'disable' { Set-Choice 'use' $false }
    'club-on' { Set-Choice 'club' $true }
    'club-off' { Set-Choice 'club' $false }
    'restore' {
        $result = & $python (Join-Path $PSScriptRoot 'title-update-profile.py') restore --state-root $state
        if ($LASTEXITCODE -ne 0) { throw "The pre-v4 profile was not restored: $(($result -join "`n" | ConvertFrom-Json).error)" }
    }
}
Get-Status | ConvertTo-Json -Compress -Depth 4
