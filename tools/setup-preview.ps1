[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateNotNullOrEmpty()] [string]$IsoPath,
    [switch]$JsonEvents,
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$resolvedIso = (Resolve-Path -LiteralPath $IsoPath).Path
$gameRoot = Resolve-PinyonLocalPath -RelativePath '.local/game/base'
$statePath = Resolve-PinyonLocalPath -RelativePath '.local/setup-state.json'
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Pinyon Shift requires 64-bit Windows.'
}
$windowsBuild = [Environment]::OSVersion.Version.Build
if ($windowsBuild -lt [int]$config.minimum_windows_build) {
    throw "Pinyon Shift requires Windows build $($config.minimum_windows_build) or newer."
}

try {
    Write-PinyonEvent verify 2 'Reading the disc image. Nothing is uploaded.' -JsonEvents:$JsonEvents
    $verification = & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso -Json |
        ConvertFrom-Json
    if (-not $verification.recognized) { throw 'This disc image is not a supported revision.' }
    Write-PinyonEvent verify 15 "Verified $($verification.serial) by exact SHA-256." -JsonEvents:$JsonEvents
    if ($VerifyOnly) { return }

    & (Join-Path $PSScriptRoot 'provision-toolchain.ps1') -JsonEvents:$JsonEvents | Out-Host
    & (Join-Path $PSScriptRoot 'prepare-rexglue.ps1') -JsonEvents:$JsonEvents | Out-Host

    Write-PinyonEvent extract 42 'Checking the local game extraction.' -JsonEvents:$JsonEvents
    $extractedValid = $false
    if (Test-Path -LiteralPath (Join-Path $gameRoot 'default.xex') -PathType Leaf) {
        try {
            $check = & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso `
                -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
            $extractedValid = [bool]$check.extracted_executables_match
        }
        catch { $extractedValid = $false }
    }
    if (-not $extractedValid) {
        if (Test-Path -LiteralPath $gameRoot) { Remove-Item -LiteralPath $gameRoot -Recurse -Force }
        [void](New-Item -ItemType Directory -Force -Path $gameRoot)
        $extractExe = Join-Path (Join-Path $root $config.extract_xiso.install_path) `
            $config.extract_xiso.executable
        Write-PinyonEvent extract 46 'Extracting your disc image locally. The original file is not modified.' -JsonEvents:$JsonEvents
        & $extractExe -q -s -x -d $gameRoot $resolvedIso
        if ($LASTEXITCODE -ne 0) { throw 'Disc-image extraction failed.' }
        $check = & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso `
            -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
        if (-not $check.extracted_executables_match) {
            throw 'Extracted game executables failed verification.'
        }
    }
    Write-PinyonEvent extract 58 'Local game files are verified and ready.' -JsonEvents:$JsonEvents

    & (Join-Path $PSScriptRoot 'build-preview.ps1') -JsonEvents:$JsonEvents | Out-Host
    $state = [ordered]@{
        schema_version = 1
        completed_utc = [DateTime]::UtcNow.ToString('o')
        dump_id = $verification.dump_id
        iso_sha256 = $verification.iso_sha256
        result = 'ready'
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    Write-PinyonEvent play 100 'Ready to play.' -JsonEvents:$JsonEvents
}
catch {
    $errorRecord = [ordered]@{
        schema_version = 1
        created_utc = [DateTime]::UtcNow.ToString('o')
        message = $_.Exception.Message
        category = [string]$_.CategoryInfo.Category
        script = $_.InvocationInfo.ScriptName
        line = $_.InvocationInfo.ScriptLineNumber
    }
    $errorPath = Join-Path $logs 'setup-error.json'
    [IO.File]::WriteAllText($errorPath, ($errorRecord | ConvertTo-Json) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    Write-Error $_
    exit 1
}
