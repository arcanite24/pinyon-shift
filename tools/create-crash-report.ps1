[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$StateRoot,
    [Parameter(Mandatory)] [string]$Executable,
    [Parameter(Mandatory)] [datetime]$StartedUtc,
    [Parameter(Mandatory)] [int64]$ProcessId,
    [Parameter(Mandatory)] [int64]$ExitCode,
    [string]$RepositoryUrl = 'https://github.com/arcanite24/pinyon-shift',
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$resolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$reportsRoot = Join-Path $resolvedStateRoot 'reports'
[void](New-Item -ItemType Directory -Force -Path $reportsRoot)

function Get-StringSha256([string]$Text) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '')
    }
    finally { $hasher.Dispose() }
}

function Get-FileSha256([string]$Path) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '') }
    finally { $stream.Dispose(); $hasher.Dispose() }
}

function Protect-ReportText([string]$Text, [hashtable]$Replacements) {
    $result = $Text
    foreach ($placeholder in $Replacements.Keys) {
        $value = [string]$Replacements[$placeholder]
        if ([string]::IsNullOrWhiteSpace($value)) { continue }
        if ($placeholder -eq '<USERNAME>') {
            $usernamePattern = '(?i)(?<![A-Z0-9_.-])' + [regex]::Escape($value) +
                '(?![A-Z0-9_.-])'
            $result = [regex]::Replace($result, $usernamePattern, [string]$placeholder)
            continue
        }
        foreach ($variant in @($value, $value.Replace('\', '/'), $value.Replace('\', '\\')) |
            Select-Object -Unique) {
            $result = [regex]::Replace($result, [regex]::Escape($variant),
                [string]$placeholder, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        }
    }
    # Catch any remaining user-profile path even if it used different separators.
    $result = [regex]::Replace($result,
        '(?i)[A-Z]:(?:\\\\|[\\/])Users(?:\\\\|[\\/])[^\\/\s"''<>]+', '<USER_PROFILE>')
    return $result
}

function Write-SanitizedTail(
    [string]$Source,
    [string]$Destination,
    [int]$MaximumLines,
    [hashtable]$Replacements
) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { return $false }
    $lines = @(Get-Content -LiteralPath $Source -Tail $MaximumLines -ErrorAction Stop)
    $content = Protect-ReportText (($lines -join [Environment]::NewLine) + [Environment]::NewLine) $Replacements
    [IO.File]::WriteAllText($Destination, $content, [Text.UTF8Encoding]::new($false))
    return $true
}

function Get-CrashDetails([string]$CrashText) {
    $header = [regex]::Match($CrashText,
        '(?im)^code=(?<code>0x[0-9a-f]+)\s+address=(?<address>(?:0x)?[0-9a-f]+)(?:\s+operation=(?<operation>\w+))?')
    $module = [regex]::Match($CrashText,
        '(?im)^fault_module=(?<module>[^\s]+)\s+fault_offset=(?<offset>0x[0-9a-f]+)')
    $frame = [regex]::Match($CrashText,
        '(?im)^#\d+\s+0x[0-9a-f]+(?:\s+(?<symbol>[^\s(]+))?')
    [ordered]@{
        exception_code = if ($header.Success) { $header.Groups['code'].Value.ToUpperInvariant() } else { $null }
        operation = if ($header.Success -and $header.Groups['operation'].Value) {
            $header.Groups['operation'].Value.ToLowerInvariant()
        } else { 'unspecified' }
        fault_module = if ($module.Success) { $module.Groups['module'].Value.ToLowerInvariant() } else { $null }
        fault_offset = if ($module.Success) { $module.Groups['offset'].Value.ToLowerInvariant() } else { $null }
        top_frame = if ($frame.Success -and $frame.Groups['symbol'].Value) {
            $frame.Groups['symbol'].Value.ToLowerInvariant()
        } else { $null }
    }
}

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) "PinyonShiftReport-$([guid]::NewGuid().ToString('N'))"
[void](New-Item -ItemType Directory -Path $stagingRoot)

$replacements = @{
    '<REPOSITORY>' = $repoRoot
    '<STATE_ROOT>' = $resolvedStateRoot
    '<GAME_ROOT>' = (Join-Path $repoRoot '.local/game/base')
    '<EXECUTABLE_DIR>' = (Split-Path $resolvedExecutable -Parent)
    '<USER_PROFILE>' = $env:USERPROFILE
    '<USERNAME>' = $env:USERNAME
}

try {
    $crashDirectory = Join-Path $resolvedStateRoot 'crashes'
    $crashFiles = if (Test-Path -LiteralPath $crashDirectory -PathType Container) {
        @(Get-ChildItem -LiteralPath $crashDirectory -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.ToUniversalTime().AddSeconds(-2) })
    } else { @() }
    $crashTextFile = $crashFiles | Where-Object Extension -eq '.txt' |
        Sort-Object @{ Expression = { $_.Name -match '-unhandled\.txt$' }; Descending = $true }, LastWriteTimeUtc |
        Select-Object -Last 1
    $crashText = if ($null -ne $crashTextFile) {
        Get-Content -LiteralPath $crashTextFile.FullName -Raw
    } else { '' }
    $details = Get-CrashDetails $crashText
    $executableHash = Get-FileSha256 $resolvedExecutable
    $identity = @(
        'pinyon-shift.crash.v1',
        "executable=$($executableHash.ToLowerInvariant())",
        "exit=$ExitCode",
        "code=$($details.exception_code)",
        "operation=$($details.operation)",
        "module=$($details.fault_module)",
        "offset=$($details.fault_offset)",
        "frame=$($details.top_frame)"
    ) -join "`n"
    $fingerprint = 'pscrash-v1-' + (Get-StringSha256 $identity).Substring(0, 20).ToLowerInvariant()

    if ($crashText) {
        [IO.File]::WriteAllText((Join-Path $stagingRoot 'crash.txt'),
            (Protect-ReportText $crashText $replacements), [Text.UTF8Encoding]::new($false))
    }

    $runtimeLog = Join-Path $resolvedStateRoot 'logs/runtime.log'
    [void](Write-SanitizedTail $runtimeLog (Join-Path $stagingRoot 'runtime-tail.log') 2500 $replacements)
    $eventLog = Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'logs') -Filter '*.jsonl' -File `
        -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.ToUniversalTime().AddSeconds(-2) } |
        Sort-Object LastWriteTimeUtc | Select-Object -Last 1
    if ($null -ne $eventLog) {
        [void](Write-SanitizedTail $eventLog.FullName (Join-Path $stagingRoot 'session-events.jsonl') 1000 $replacements)
    }

    $xmaStallColumns = @(
        'xma_no_space_stalls', 'xma_no_progress_stalls', 'xma_stall_recoveries'
    )
    $xmaStalls = [ordered]@{
        available = $false
        no_space = [uint64]0
        no_progress = [uint64]0
        recoveries = [uint64]0
    }
    $zpdColumns = @(
        'zpd_reports_started', 'zpd_reports_ended', 'zpd_report_segments',
        'zpd_same_slot_reuse', 'zpd_fast_speculative_writes',
        'zpd_async_result_patches', 'zpd_strict_waits',
        'zpd_strict_wait_time_ns', 'zpd_retire_timeouts', 'zpd_fake_fallbacks',
        'zpd_malformed_records', 'zpd_stale_result_rejections',
        'zpd_classified_begins', 'zpd_classified_ends',
        'zpd_classified_orphaned_ends', 'zpd_policy_fallbacks',
        'zpd_watchdog_recoveries'
    )
    $zpdCounters = [ordered]@{ available = $false }
    foreach ($column in $zpdColumns) { $zpdCounters[$column] = [uint64]0 }
    $presentationColumns = @(
        'guest_vblank_count', 'guest_vblank_delta_ns',
        'simulation_tick_count', 'present_count', 'present_delta_ns',
        'present_queue_depth', 'present_deadline_misses',
        'duplicate_present_count', 'dropped_present_count'
    )
    $presentationCounters = [ordered]@{ available = $false }
    foreach ($column in $presentationColumns) {
        $presentationCounters[$column] = [uint64]0
    }
    $perfLog = Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'logs') -Filter '*.perf.csv' -File `
        -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.ToUniversalTime().AddSeconds(-2) } |
        Sort-Object LastWriteTimeUtc | Select-Object -Last 1
    if ($null -ne $perfLog) {
        $header = @(Get-Content -LiteralPath $perfLog.FullName -TotalCount 1 -ErrorAction SilentlyContinue)
        $columns = if ($header.Count -eq 1) { @($header[0].Split(',')) } else { @() }
        if (@($xmaStallColumns | Where-Object { $_ -notin $columns }).Count -eq 0) {
            foreach ($row in Import-Csv -LiteralPath $perfLog.FullName) {
                $xmaStalls.no_space += [uint64]$row.xma_no_space_stalls
                $xmaStalls.no_progress += [uint64]$row.xma_no_progress_stalls
                $xmaStalls.recoveries += [uint64]$row.xma_stall_recoveries
            }
            $xmaStalls.available = $true
        }
        if (@($zpdColumns | Where-Object { $_ -notin $columns }).Count -eq 0) {
            foreach ($row in Import-Csv -LiteralPath $perfLog.FullName) {
                foreach ($column in $zpdColumns) {
                    $zpdCounters[$column] += [uint64]$row.$column
                }
            }
            $zpdCounters.available = $true
        }
        if (@($presentationColumns | Where-Object { $_ -notin $columns }).Count -eq 0) {
            foreach ($row in Import-Csv -LiteralPath $perfLog.FullName) {
                foreach ($column in $presentationColumns) {
                    $presentationCounters[$column] += [uint64]$row.$column
                }
            }
            $presentationCounters.available = $true
        }
    }
    $resolveColumns = @(
        'resolve_readback_requests', 'resolve_readback_bytes',
        'resolve_readback_fast_copies', 'resolve_readback_cache_misses',
        'resolve_readback_full_waits', 'resolve_readback_wait_time_ns'
    )
    $resolveCounters = [ordered]@{ available = $false }
    foreach ($column in $resolveColumns) { $resolveCounters[$column] = [uint64]0 }
    if ($perfLog) {
        $columns = @((Get-Content -LiteralPath $perfLog.FullName -TotalCount 1) -split ',')
        if (@($resolveColumns | Where-Object { $_ -notin $columns }).Count -eq 0) {
            foreach ($row in Import-Csv -LiteralPath $perfLog.FullName) {
                foreach ($column in $resolveColumns) {
                    $resolveCounters[$column] += [uint64]$row.$column
                }
            }
            $resolveCounters.available = $true
        }
    }

    $allowedSettings = @(
        'pinyon_shift_config_schema', 'input_backend', 'hid_mappings_file',
        'mnk_mode', 'keybind_start',
        'd3d12_allow_variable_refresh_rate_and_tearing',
        'xma_relaxed_padding_admission',
        'pinyon_shift_capture_performance',
        'pinyon_shift_stabilize_vehicle_presentation', 'pinyon_shift_skip_opening_movies',
        'resolution', 'vsync', 'host_present_fps_limit',
        'host_present_sleep_spin', 'anisotropic_override', 'swap_post_effect',
        'draw_resolution_scale_x', 'draw_resolution_scale_y', 'occlusion_query',
        'zpd_end_policy', 'zpd_end_fallback', 'clear_memory_page_state',
        'readback_resolve', 'readback_resolve_half_pixel_offset',
        'readback_memexport', 'readback_memexport_fast'
    )
    $configPath = Join-Path $resolvedStateRoot 'config/pinyon_shift.toml'
    $settings = [ordered]@{}
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $configPath) {
            if ($line -match '^\s*(?<key>[a-zA-Z0-9_]+)\s*=\s*(?<value>.+?)\s*(?:#.*)?$' -and
                $Matches.key -in $allowedSettings) {
                $settings[$Matches.key] = $Matches.value
            }
        }
    }

    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue | Select-Object -First 1
    $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
    $gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
        Select-Object Name, DriverVersion)
    $runtimeDirectory = Split-Path $resolvedExecutable -Parent
    $release = if (Test-Path -LiteralPath (Join-Path $repoRoot 'config/release.json')) {
        Get-Content -LiteralPath (Join-Path $repoRoot 'config/release.json') -Raw | ConvertFrom-Json
    } else { $null }
    $setupState = if (Test-Path -LiteralPath (Join-Path $repoRoot '.local/setup-state.json')) {
        Get-Content -LiteralPath (Join-Path $repoRoot '.local/setup-state.json') -Raw | ConvertFrom-Json
    } else { $null }
    $binaryHashes = [ordered]@{}
    foreach ($name in @('pinyon_shift.exe', 'rexruntime.dll', 'rexgpu-xenos.dll',
        'pinyon_shift_SpeechFacade_default.dll', 'pinyon_shift_XMediaFacade_default.dll')) {
        $path = Join-Path $runtimeDirectory $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $binaryHashes[$name] = Get-FileSha256 $path
        }
    }
    $buildProvenancePath = Join-Path $runtimeDirectory 'pinyon_shift_build.json'
    $buildProvenance = if (Test-Path -LiteralPath $buildProvenancePath -PathType Leaf) {
        Get-Content -LiteralPath $buildProvenancePath -Raw | ConvertFrom-Json
    } else { $null }
    $dumpRecords = @($crashFiles | Where-Object Extension -eq '.dmp' | ForEach-Object {
        [ordered]@{
            name = $_.Name
            size_bytes = $_.Length
            sha256 = Get-FileSha256 $_.FullName
            sharing = 'kept_local_not_included'
        }
    })
    $manifest = [ordered]@{
        schema = 'pinyon-shift.crash-report.v1'
        created_utc = [DateTime]::UtcNow.ToString('o')
        crash_id = $fingerprint
        process = [ordered]@{
            process_id = $ProcessId
            started_utc = $StartedUtc.ToUniversalTime().ToString('o')
            exit_code_signed = $ExitCode
            exit_code_hex = ('0x{0:X8}' -f ([uint32]($ExitCode -band 0xFFFFFFFFL)))
        }
        exception = $details
        build = [ordered]@{
            binaries = $binaryHashes
            provenance = $buildProvenance
        }
        release = [ordered]@{
            version = if ($release) { $release.version } else { $null }
            channel = if ($release) { $release.channel } else { $null }
            dump_id = if ($setupState) { $setupState.dump_id } else { $null }
        }
        system = [ordered]@{
            os = if ($os) { $os.Caption } else { $null }
            os_version = if ($os) { $os.Version } else { $null }
            os_build = if ($os) { $os.BuildNumber } else { $null }
            cpu = if ($cpu) { $cpu.Name } else { $null }
            logical_processors = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
            memory_bytes = if ($os) { [uint64]$os.TotalVisibleMemorySize * 1KB } else { $null }
            gpu = $gpus
        }
        settings = $settings
        audio = [ordered]@{
            xma_stalls = $xmaStalls
        }
        graphics = [ordered]@{
            zpd = $zpdCounters
            resolve_readback = $resolveCounters
            presentation = $presentationCounters
        }
        local_dumps = $dumpRecords
        privacy = [ordered]@{
            paths_redacted = $true
            game_files_included = $false
            save_data_included = $false
            generated_code_included = $false
            memory_dump_included = $false
            input_capture_included = $false
            audio_payload_included = $false
        }
    }
    [IO.File]::WriteAllText((Join-Path $stagingRoot 'report.json'),
        ($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))

    $title = "[Crash] $fingerprint"
    $body = @(
        '### What happened?',
        '',
        '<!-- Tell us what you were doing immediately before the crash. -->',
        '',
        '### Reproduction steps',
        '',
        '1. ',
        '2. ',
        '3. ',
        '',
        '### Crash details',
        '',
        "- Crash ID: ``$fingerprint``",
        "- Exit code: ``$($manifest.process.exit_code_hex)``",
        "- Exception: ``$($details.exception_code)``",
        "- Windows build: ``$($manifest.system.os_build)``",
        "- GPU: ``$(@($gpus.Name) -join '; ')``",
        '',
        '### Diagnostic report',
        '',
        '<!-- Drag the ZIP selected by the launcher into this issue. It excludes game files, saves, generated code, and memory dumps. -->'
    ) -join "`n"
    [IO.File]::WriteAllText((Join-Path $stagingRoot 'issue-body.md'), $body,
        [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $stagingRoot 'README.txt'),
        "Attach this ZIP to the GitHub issue opened by the launcher.`r`nNo game files, saves, generated code, input capture, or memory dumps are included.`r`nLocal crash dumps remain only in your crashes folder for private follow-up.`r`n",
        [Text.UTF8Encoding]::new($false))

    foreach ($file in Get-ChildItem -LiteralPath $stagingRoot -Recurse -File) {
        if ($file.Extension.ToLowerInvariant() -in @('.dmp', '.exe', '.dll', '.iso', '.xex', '.obj', '.lib', '.pdb')) {
            throw "Forbidden diagnostic attachment: $($file.Name)"
        }
        $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
        $usernamePattern = if ($env:USERNAME) {
            '(?i)(?<![A-Z0-9_.-])' + [regex]::Escape($env:USERNAME) + '(?![A-Z0-9_.-])'
        } else { $null }
        if ($content -and $usernamePattern -and $content -match $usernamePattern) {
            throw "A local user name remained in the diagnostic report: $($file.Name)"
        }
    }

    $archivePath = Join-Path $reportsRoot "PinyonShift-$fingerprint-$timestamp.zip"
    Compress-Archive -Path (Join-Path $stagingRoot '*') -DestinationPath $archivePath -CompressionLevel Optimal
    $issueUrl = "$RepositoryUrl/issues/new?title=$([Uri]::EscapeDataString($title))&body=$([Uri]::EscapeDataString($body))&labels=crash"
    $pending = [ordered]@{
        schema = 1
        created_utc = [DateTime]::UtcNow.ToString('o')
        crash_id = $fingerprint
        bundle = $archivePath
        issue_url = $issueUrl
        exit_code_hex = $manifest.process.exit_code_hex
    }
    [IO.File]::WriteAllText((Join-Path $reportsRoot 'pending-report.json'),
        ($pending | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false))

    if ($Json) { $pending | ConvertTo-Json -Compress }
    else { $pending }
}
finally {
    $resolvedStaging = [IO.Path]::GetFullPath($stagingRoot)
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') + '\'
    if ($resolvedStaging.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path $resolvedStaging -Leaf).StartsWith('PinyonShiftReport-')) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
