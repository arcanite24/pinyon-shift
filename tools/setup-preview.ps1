[CmdletBinding()]
param(
    [Parameter(Mandatory, ParameterSetName = 'Iso')] [ValidateNotNullOrEmpty()] [string]$IsoPath,
    [Parameter(Mandatory, ParameterSetName = 'Extracted')] [Alias('GamePath', 'GameDir')]
    [ValidateNotNullOrEmpty()] [string]$ExtractedPath,
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
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)
$errorPath = Join-Path $logs 'setup-error.json'
# A report from an earlier attempt must not be mistaken for this one.
if (Test-Path -LiteralPath $errorPath) { Remove-Item -LiteralPath $errorPath -Force }

try {
    $config = Get-PinyonReleaseToolchain
    $folderInput = $PSCmdlet.ParameterSetName -eq 'Extracted'
    $resolvedIso = if ($folderInput) { $null } else { (Resolve-Path -LiteralPath $IsoPath).Path }
    $resolvedSource = if ($folderInput) { (Resolve-Path -LiteralPath $ExtractedPath).Path } else { $resolvedIso }
    $gameRoot = Resolve-PinyonLocalPath -RelativePath '.local/game/base'
    $statePath = Resolve-PinyonLocalPath -RelativePath '.local/setup-state.json'
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Pinyon Shift requires 64-bit Windows.'
    }
    $windowsBuild = [Environment]::OSVersion.Version.Build
    if ($windowsBuild -lt [int]$config.minimum_windows_build) {
        throw "Pinyon Shift requires Windows build $($config.minimum_windows_build) or newer."
    }

    $runningPreview = @(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue)
    if ($runningPreview.Count -gt 0) {
        throw 'Close every running Pinyon Shift preview before building. Windows locks the runtime files while the game is open.'
    }
    # Tools built beside the game (for example the archive extractor used
    # while preparing graphics) load the same runtime DLL.
    $buildTree = [IO.Path]::GetFullPath((Join-Path $root 'out/build')).TrimEnd('\', '/') +
        [IO.Path]::DirectorySeparatorChar
    $buildTreeProcesses = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $path = $null
        try { $path = $_.Path } catch { }
        $path -and $path.StartsWith($buildTree, [StringComparison]::OrdinalIgnoreCase)
    })
    if ($buildTreeProcesses.Count -gt 0) {
        $names = ($buildTreeProcesses | ForEach-Object { "$($_.ProcessName).exe (PID $($_.Id))" }) -join ', '
        throw "Close $names before building. It was started from the Pinyon Shift build folder and keeps its runtime files locked."
    }
    Write-PinyonEvent verify 2 'Reading your game source. Nothing is uploaded.' -JsonEvents:$JsonEvents
    $verification = if ($folderInput) {
        & (Join-Path $PSScriptRoot 'verify-extracted-game.ps1') -ExtractedRoot $resolvedSource -Json | ConvertFrom-Json
    } else {
        & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso -Json | ConvertFrom-Json
    }
    if (-not $verification.recognized) { throw 'This game source is not a supported, complete retail revision.' }
    Write-PinyonEvent verify 15 "Verified $($verification.serial) by exact SHA-256." -JsonEvents:$JsonEvents
    if ($VerifyOnly) { return }

    & (Join-Path $PSScriptRoot 'provision-toolchain.ps1') -JsonEvents:$JsonEvents | Out-Host
    & (Join-Path $PSScriptRoot 'prepare-rexglue.ps1') -JsonEvents:$JsonEvents | Out-Host

    Write-PinyonEvent extract 42 'Checking the local game extraction.' -JsonEvents:$JsonEvents
    $extractedValid = $false
    if (Test-Path -LiteralPath (Join-Path $gameRoot 'default.xex') -PathType Leaf) {
        try {
            $check = if ($folderInput) {
                & (Join-Path $PSScriptRoot 'verify-extracted-game.ps1') -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
            } else {
                & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
            }
            $extractedValid = [bool]$check.extracted_executables_match
        }
        catch { $extractedValid = $false }
    }
    if (-not $extractedValid) {
        $checkedGameRoot = [IO.Path]::GetFullPath($gameRoot).TrimEnd('\', '/')
        $intendedGameRoot = [IO.Path]::GetFullPath((Join-Path $root '.local/game/base')).TrimEnd('\', '/')
        if ($checkedGameRoot -ne $intendedGameRoot) { throw 'Unexpected local game destination.' }
        if ((Test-Path -LiteralPath $checkedGameRoot) -and
            ((Get-Item -LiteralPath $checkedGameRoot).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The local game destination must not be a link or junction.'
        }
        if ($folderInput) {
            $sourcePrefix = $resolvedSource.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
            $targetPrefix = $checkedGameRoot + [IO.Path]::DirectorySeparatorChar
            if ($sourcePrefix.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase) -or
                $targetPrefix.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'The extracted source must be separate from the local game destination.'
            }
        }
        if (Test-Path -LiteralPath $gameRoot) { Remove-Item -LiteralPath $checkedGameRoot -Recurse -Force }
        [void](New-Item -ItemType Directory -Force -Path $gameRoot)
        if ($folderInput) {
            Write-PinyonEvent extract 46 'Copying verified game files locally. The source folder is not modified.' -JsonEvents:$JsonEvents
            foreach ($item in Get-ChildItem -LiteralPath $resolvedSource -Force) {
                if ($item.Name -ne '$SystemUpdate') {
                    Copy-Item -LiteralPath $item.FullName -Destination $gameRoot -Recurse
                }
            }
            $check = & (Join-Path $PSScriptRoot 'verify-extracted-game.ps1') -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
        } else {
            $extractExe = Join-Path (Join-Path $root $config.extract_xiso.install_path) `
                $config.extract_xiso.executable
            Write-PinyonEvent extract 46 'Extracting your disc image locally. The original file is not modified.' -JsonEvents:$JsonEvents
            & $extractExe -q -s -x -d $gameRoot $resolvedIso
            if ($LASTEXITCODE -ne 0) { throw 'Disc-image extraction failed.' }
            $check = & (Join-Path $PSScriptRoot 'verify-game.ps1') -IsoPath $resolvedIso `
                -ExtractedRoot $gameRoot -Json | ConvertFrom-Json
        }
        if (-not $check.recognized -or -not $check.extracted_executables_match) {
            throw 'Extracted game executables failed verification.'
        }
    }
    Write-PinyonEvent extract 58 'Local game files are verified and ready.' -JsonEvents:$JsonEvents

    & (Join-Path $PSScriptRoot 'build-preview.ps1') -JsonEvents:$JsonEvents | Out-Host
    & (Join-Path $PSScriptRoot 'prepare-fh1-shaders.ps1') -GameRoot $gameRoot -JsonEvents:$JsonEvents | Out-Host
    $state = [ordered]@{
        schema_version = 1
        completed_utc = [DateTime]::UtcNow.ToString('o')
        dump_id = $verification.dump_id
        source_kind = if ($folderInput) { 'extracted' } else { 'iso' }
        iso_sha256 = $verification.iso_sha256
        result = 'ready'
    }
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))
    Write-PinyonEvent play 100 'Ready to play.' -JsonEvents:$JsonEvents
}
catch {
    # Report the failure as plain text and exit with a code. Write-Error under
    # $ErrorActionPreference = 'Stop' turns into a second, terminating error
    # whose position is the Write-Error line itself ("At ...:92 char:5"),
    # which hides the real step and its output.
    $failure = $_
    $errorRecord = $null
    try {
        $errorRecord = New-PinyonFailureRecord -ErrorRecord $failure
        $errorRecord.system = Get-PinyonSystemSummary -Root $root
        [IO.File]::WriteAllText($errorPath, ($errorRecord | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
        foreach ($line in (Format-PinyonFailureRecord -Record $errorRecord)) { [Console]::Out.WriteLine($line) }
        [Console]::Out.WriteLine("Failure details: $errorPath")
    }
    catch {
        [Console]::Out.WriteLine("Setup failed: $($failure.Exception.Message)")
        [Console]::Out.WriteLine("The failure report could not be written: $($_.Exception.Message)")
    }
    [Console]::Out.Flush()
    [Console]::Error.WriteLine("Setup failed: $($failure.Exception.Message)")
    exit 1
}
