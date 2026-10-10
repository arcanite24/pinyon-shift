[CmdletBinding()]
param(
    [ValidateSet('Release', 'RelWithDebInfo')]
    [string]$Configuration = 'Release',
    [string]$GameRoot,
    [string]$StateRoot,
    [string]$BuildDirectory,
    [string]$ShaderCaptureDir,
    [string]$DiscShaderCorpusDir,
    [string]$RenderTestScript,
    [string]$RenderTestOutput,
    [string]$RenderDocCommand,
    [string]$RenderDocCapturePrefix,
    # Nsight Graphics GPU Trace: ngfx.exe, the folder for the trace, and the
    # frame (presents counted from the start) to trace.
    [string]$NsightCommand,
    [string]$NsightOutputDir,
    [int]$NsightStartAfterFrames = 0,
    [ValidateRange(1, 10)]
    [int]$NsightFrames = 1,
    [ValidateRange(1, 3600)]
    [int]$RenderTestTimeoutSeconds,
    [switch]$CollectFh1PassInventory,
    [switch]$SkipShaderPreparation,
    # Render tests can exercise the same owned-entry preflight as normal play.
    [switch]$VerifyRally,
    [switch]$RenderTestIncludeOpeningMovies,
    [switch]$DirectChildProcess,
    [string[]]$GameArguments = @(),
    [string]$GameArgumentsJson,
    [switch]$Json,
    [switch]$JsonEvents,
    [switch]$Hidden,
    [switch]$CrashSelfTest,
    # Developer build of the FH1 v4 title update (TITLE_UPDATE_V4_BACKLOG):
    # runs out/build/win-amd64-v4 with the verified update in
    # <state>/title-update-v4. The expansion's own code replaces the
    # base-disc Rally preparation.
    [switch]$TitleUpdateV4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$resolvedBuildDirectory = if ($BuildDirectory) {
    (Resolve-Path -LiteralPath $BuildDirectory).Path
} elseif ($TitleUpdateV4) {
    Join-Path $repoRoot 'out/build/win-amd64-v4'
} else {
    Join-Path $repoRoot ('out/build/win-amd64-' + $Configuration.ToLowerInvariant())
}
$executable = Join-Path $resolvedBuildDirectory 'pinyon_shift.exe'
$resolvedGameRoot = if ($GameRoot) {
    [IO.Path]::GetFullPath($GameRoot)
} else {
    Join-Path $repoRoot '.local/game/base'
}
$resolvedStateRoot = if ($StateRoot) {
    [IO.Path]::GetFullPath($StateRoot)
} else {
    Join-Path $repoRoot '.local/preview'
}

if ($TitleUpdateV4) {
    $titleUpdate = Join-Path $resolvedStateRoot 'title-update-v4'
    foreach ($name in 'default.xexp', 'SpeechFacade_default.xexp', 'XMediaFacade_default.xexp', 'media.zip') {
        if (-not (Test-Path -LiteralPath (Join-Path $titleUpdate $name) -PathType Leaf)) {
            throw "The v4 build needs the verified title update in $titleUpdate. Install it with tools/verify-fh1-title-update.py --install."
        }
    }
    # A v4 save is one-way: the base build cannot load it afterwards. Keep a
    # verified copy of every base-version profile before its first v4 load;
    # tools/title-update-profile.py restore brings it back.
    $profileBackup = & (Get-PinyonPython) (Join-Path $PSScriptRoot 'title-update-profile.py') backup `
        --state-root $resolvedStateRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not back up the profile before its first v4 load: $profileBackup"
    }
    Write-Host 'FH1 v4 title update: saves written by this build cannot be loaded by the base build.'
    # Optional offline 1000 Club (TITLE_UPDATE_V4_BACKLOG TU-7), chosen in the
    # launcher: report a LIVE sign-in, answer 1000 Club's server checks and
    # confirm completed goals locally. Render tests pass these flags explicitly.
    $choice = Join-Path $resolvedStateRoot 'config/title-update.json'
    if (-not $RenderTestScript -and (Test-Path -LiteralPath $choice -PathType Leaf)) {
        $settings = Get-Content -LiteralPath $choice -Raw | ConvertFrom-Json
        if ($settings.PSObject.Properties['club'] -and [bool]$settings.club) {
            $GameArguments = @($GameArguments) + @('--pinyon_shift_car_challenge_gate_probe=true',
                '--xam_report_live_signin=true')
            Write-Host 'FH1 v4 title update: 1000 Club runs offline.'
        }
    }
}
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'The preview has not been built. Run tools/setup-preview.ps1 first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedGameRoot 'default.xex') -PathType Leaf)) {
    throw "Game files are missing at $resolvedGameRoot. Select your disc image in the launcher and run setup to restore them. Your save will be preserved."
}
if (@(Get-Process -Name 'pinyon_shift' -ErrorAction SilentlyContinue).Count -ne 0) {
    throw 'Pinyon Shift is already running.'
}

foreach ($directory in @('', 'cache', 'config', 'crashes', 'logs', 'reports', 'update', 'user')) {
    $path = if ($directory) { Join-Path $resolvedStateRoot $directory } else { $resolvedStateRoot }
    [void](New-Item -ItemType Directory -Force -Path $path)
}
$pendingReport = Join-Path $resolvedStateRoot 'reports/pending-report.json'
if (Test-Path -LiteralPath $pendingReport -PathType Leaf) {
    Remove-Item -LiteralPath $pendingReport -Force
}

$stagedNativeShaderPack = $null
$stagedNativePipelineCache = $null
$stagedShaderProducer = $null
if ($DiscShaderCorpusDir) {
    # Plugins carry the build type's postfix (PluginFileName in the SDK).
    $buildType = 'Release'
    $cache = Join-Path $resolvedBuildDirectory 'CMakeCache.txt'
    if (Test-Path -LiteralPath $cache -PathType Leaf) {
        $line = Select-String -LiteralPath $cache -Pattern '^CMAKE_BUILD_TYPE:STRING=(.+)$' |
            Select-Object -First 1
        if ($line) { $buildType = $line.Matches[0].Groups[1].Value }
    }
    $pluginPostfix = switch ($buildType) { 'Debug' { 'd' } 'RelWithDebInfo' { 'rd' } default { '' } }
    $producerName = "rexgpu-fh1-producer$pluginPostfix.dll"
    $producerSource = Join-Path $resolvedBuildDirectory "rexglue-artifacts/$producerName"
    if (-not (Test-Path -LiteralPath $producerSource -PathType Leaf)) {
        throw 'Build the rexgpu-fh1-producer target before producing FH1 shaders.'
    }
    $stagedShaderProducer = Join-Path (Split-Path $executable -Parent) $producerName
}
if (-not ($RenderTestScript -or $ShaderCaptureDir -or $DiscShaderCorpusDir -or $CrashSelfTest -or $SkipShaderPreparation)) {
    & (Join-Path $PSScriptRoot 'prepare-fh1-shaders.ps1') -StateRoot $resolvedStateRoot `
        -GameRoot $resolvedGameRoot -BuildDirectory $resolvedBuildDirectory -JsonEvents:$JsonEvents
    $stagedNativeShaderPack = Join-Path $resolvedStateRoot 'cache/fh1-artifacts.json'
    $stagedNativePipelineCache = Join-Path $resolvedStateRoot 'cache'
}

# Mods' database patches (NP-10.2) are applied to a copy of the player's own
# gamedb.slt before each start, so they follow the enabled mods. The same
# step installs the project's built-in optional mods (the immersive camera).
& (Get-PinyonPython) (Join-Path $PSScriptRoot 'build-mod-patches.py') $resolvedStateRoot `
    --game-root $resolvedGameRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not build the mods'' database patches.' }
# Mods' single archive members (NP-10.1) and key merges (NP-10.2), rebuilt
# into copies of the player's archives with zipmanifest.xml to match; the
# archive extractor decompresses members that merges edit.
$archiveArguments = @('--game-root', $resolvedGameRoot)
$archiveExtractor = Join-Path $resolvedBuildDirectory 'pinyon_shift_fh1_archive_extract.exe'
if (Test-Path -LiteralPath $archiveExtractor -PathType Leaf) {
    $archiveArguments += @('--archive-extractor', $archiveExtractor)
}
& (Get-PinyonPython) (Join-Path $PSScriptRoot 'build-mod-archives.py') $resolvedStateRoot `
    @archiveArguments | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not build the mods'' archive members.' }

# Verify owned Rally and its generated cache before normal play. Diagnostic
# scenarios retain their private overlays; no probe flag is needed by players.
$verifiedRallyEntry = $false
if (-not $TitleUpdateV4 -and ($VerifyRally -or -not ($RenderTestScript -or $ShaderCaptureDir -or $DiscShaderCorpusDir -or $CrashSelfTest))) {
    $rallyContent = Join-Path $resolvedStateRoot 'user/0000000000000000/4D5309C9/00000002/6F6992766050D818245ADD408031E280FB5F4E634D'
    if (Test-Path -LiteralPath $rallyContent -PathType Container) {
        $rallyResult = & (Get-PinyonPython) (Join-Path $PSScriptRoot 'prepare-fh1-rally.py') `
            --state-root $resolvedStateRoot --game-root $resolvedGameRoot `
            --extractor (Join-Path $resolvedBuildDirectory 'pinyon_shift_fh1_archive_extract.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Could not verify and prepare Rally. Restore or re-import the verified Rally package in the DLC panel. Saved cars with Rally parts require this content.' }
        $verifiedRallyEntry = (ConvertFrom-Json -InputObject ($rallyResult -join "`n")).entry_ready -eq $true
    }
}

$savedRallyPrepared = $env:PINYON_SHIFT_RALLY_PREPARED
$savedStateRoot = $env:PINYON_SHIFT_STATE_ROOT
$savedGameRoot = $env:PINYON_SHIFT_GAME_ROOT
$savedTearing = $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING
$savedCrashTest = $env:PINYON_SHIFT_CRASH_SELF_TEST
$savedShaderCaptureDir = $env:PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR
$savedDiscShaderCorpusDir = $env:PINYON_SHIFT_FH1_DISC_SHADER_CORPUS_DIR
$savedRenderTestScript = $env:PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT
$savedRenderTestOutput = $env:PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT
$savedWindowHidden = $env:REX_WINDOW_HIDDEN
$startedUtc = [DateTime]::UtcNow
$process = $null
try {
    $env:REX_WINDOW_HIDDEN = if ($Hidden) { '1' } else { $null }
    if ($stagedShaderProducer) {
        Copy-Item -LiteralPath $producerSource -Destination $stagedShaderProducer -Force
    }
    $env:PINYON_SHIFT_STATE_ROOT = $resolvedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $resolvedGameRoot
    $env:PINYON_SHIFT_RALLY_PREPARED = if ($verifiedRallyEntry) { '1' } else { $null }
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = 'false'
    $env:PINYON_SHIFT_CRASH_SELF_TEST = if ($CrashSelfTest) { '1' } else { $null }
    $env:PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR = if ($ShaderCaptureDir) {
        [IO.Path]::GetFullPath($ShaderCaptureDir)
    } else {
        $null
    }
    $env:PINYON_SHIFT_FH1_DISC_SHADER_CORPUS_DIR = if ($DiscShaderCorpusDir) {
        (Resolve-Path -LiteralPath $DiscShaderCorpusDir).Path
    } else {
        $null
    }
    $env:PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT = if ($RenderTestScript) {
        (Resolve-Path -LiteralPath $RenderTestScript).Path
    } else {
        $null
    }
    $env:PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT = if ($RenderTestOutput) {
        [IO.Path]::GetFullPath($RenderTestOutput)
    } else {
        $null
    }
    $start = @{
        FilePath = $executable
        WorkingDirectory = (Split-Path $executable -Parent)
        PassThru = $true
    }
    $normalizedGameArguments = @($GameArguments)
    if ($Hidden) {
        if (-not $DirectChildProcess) { $start.WindowStyle = 'Hidden' }
        $normalizedGameArguments += '--audio_mute=true'
    }
    if ($GameArgumentsJson) {
        foreach ($gameArgument in (ConvertFrom-Json -InputObject $GameArgumentsJson)) {
            $normalizedGameArguments += [string]$gameArgument
        }
    }
    if ($RenderTestScript) {
        if (-not $RenderTestIncludeOpeningMovies) {
            $normalizedGameArguments += '--pinyon_shift_skip_opening_movies=true'
        }
    }
    if ($CollectFh1PassInventory) {
        $normalizedGameArguments += '--pinyon_shift_fh1_gpu_corpus=true'
    }
    if ($normalizedGameArguments.Count -ne 0) {
        $start.ArgumentList = $normalizedGameArguments
    }
    if ($RenderDocCommand) {
        if (-not $RenderDocCapturePrefix) {
            throw '-RenderDocCapturePrefix is required with -RenderDocCommand.'
        }
        $start.FilePath = (Resolve-Path -LiteralPath $RenderDocCommand).Path
        $start.ArgumentList = @('capture', '--wait-for-exit',
            '-d', (Split-Path $executable -Parent), '-c',
            [IO.Path]::GetFullPath($RenderDocCapturePrefix), $executable) +
            $normalizedGameArguments
    }
    if ($NsightCommand) {
        if (-not $NsightOutputDir) { throw '-NsightOutputDir is required with -NsightCommand.' }
        if ($RenderDocCommand) { throw '-NsightCommand and -RenderDocCommand are exclusive.' }
        $start.FilePath = (Resolve-Path -LiteralPath $NsightCommand).Path
        $start.ArgumentList = @('--activity', '"GPU Trace Profiler"',
            '--exe', ('"' + $executable + '"'), '--dir', ('"' + (Split-Path $executable -Parent) + '"'),
            '--args', ('"' + ($normalizedGameArguments -join ' ') + '"'),
            '--start-after-frames', [string]$NsightStartAfterFrames,
            '--limit-to-frames', [string]$NsightFrames,
            '--auto-export', '--output-dir', ('"' + [IO.Path]::GetFullPath($NsightOutputDir) + '"'))
        # ngfx reports why a trace failed only on its own output, in the trace folder.
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($NsightOutputDir))
        $start.RedirectStandardOutput = Join-Path ([IO.Path]::GetFullPath($NsightOutputDir)) 'ngfx.log'
        $start.RedirectStandardError = Join-Path ([IO.Path]::GetFullPath($NsightOutputDir)) 'ngfx.err.log'
    }
    if ($DirectChildProcess) {
        # Keep capture/debugger child-process hooks on the launching process.
        $start.NoNewWindow = $true
    }
    if ($JsonEvents) { Write-PinyonEvent play 100 'Starting game.' -JsonEvents }
    $process = Start-Process @start
    if ($DirectChildProcess) {
        # Cache the live handle so ExitCode remains available after exit.
        $null = $process.Handle
    }
    if ($RenderTestTimeoutSeconds) {
        if (-not $process.WaitForExit($RenderTestTimeoutSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
            throw "Pinyon Shift render test timed out after $RenderTestTimeoutSeconds seconds."
        }
    } else {
        $process.WaitForExit()
    }
    $process.Refresh()
}
finally {
    $env:PINYON_SHIFT_STATE_ROOT = $savedStateRoot
    $env:PINYON_SHIFT_GAME_ROOT = $savedGameRoot
    $env:PINYON_SHIFT_RALLY_PREPARED = $savedRallyPrepared
    $env:REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING = $savedTearing
    $env:PINYON_SHIFT_CRASH_SELF_TEST = $savedCrashTest
    $env:PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR = $savedShaderCaptureDir
    $env:PINYON_SHIFT_FH1_DISC_SHADER_CORPUS_DIR = $savedDiscShaderCorpusDir
    $env:PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT = $savedRenderTestScript
    $env:PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT = $savedRenderTestOutput
    $env:REX_WINDOW_HIDDEN = $savedWindowHidden
    if ($stagedShaderProducer) {
        Remove-Item -LiteralPath $stagedShaderProducer -Force -ErrorAction SilentlyContinue
    }
}

if ($null -eq $process) { throw 'Windows did not start Pinyon Shift.' }
$exitCode = [int64]$process.ExitCode
if ($RenderDocCommand) {
    $result = [ordered]@{
        result = if ($exitCode -eq 0) { 'capture-wrapper-exit' } else { 'capture-wrapper-failed' }
        process_id = $process.Id
        exit_code = $exitCode
        capture_prefix = [IO.Path]::GetFullPath($RenderDocCapturePrefix)
    }
    if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
    if ($exitCode -ne 0) { exit 1 }
    return
}
if ($exitCode -eq 1308) {
    # The graphics device did not start: a driver without Vulkan 1.3 or a GPU
    # that has none. The game said so; a crash report would not help.
    $result = [ordered]@{
        result = 'graphics-unavailable'
        process_id = $process.Id
        exit_code = $exitCode
    }
    if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
    exit 1
}
if ($exitCode -eq 1307) {
    # The game stopped before dereferencing a missing saved tyre record.
    # This needs the player's content restored, not a crash report.
    $result = [ordered]@{
        result = 'saved-content-unavailable'
        process_id = $process.Id
        exit_code = $exitCode
    }
    if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
    exit 1
}
if ($exitCode -ne 0) {
    $report = & (Join-Path $PSScriptRoot 'create-crash-report.ps1') `
        -StateRoot $resolvedStateRoot -Executable $executable `
        -StartedUtc $startedUtc -ProcessId $process.Id -ExitCode $exitCode -Json |
        ConvertFrom-Json
    $result = [ordered]@{
        result = 'crash'
        process_id = $process.Id
        exit_code = $exitCode
        crash_id = $report.crash_id
        bundle = $report.bundle
        issue_url = $report.issue_url
    }
    if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
    exit 1
}

$result = [ordered]@{
    result = 'normal-exit'
    process_id = $process.Id
    exit_code = $exitCode
    native_shader_pack = $stagedNativeShaderPack
    native_pipeline_cache = $stagedNativePipelineCache
}
if ($Json) { $result | ConvertTo-Json -Compress } else { $result }
