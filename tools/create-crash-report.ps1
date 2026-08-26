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

    $allowedSettings = @(
        'pinyon_shift_config_schema', 'input_backend', 'hid_mappings_file',
        'mnk_mode', 'keybind_start',
        'd3d12_allow_variable_refresh_rate_and_tearing',
        'pinyon_shift_stabilize_vehicle_presentation', 'pinyon_shift_skip_opening_movies',
        'resolution', 'vsync', 'anisotropic_override', 'swap_post_effect',
        'draw_resolution_scale_x', 'draw_resolution_scale_y'
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
        build = $binaryHashes
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
        local_dumps = $dumpRecords
        privacy = [ordered]@{
            paths_redacted = $true
            game_files_included = $false
            save_data_included = $false
            generated_code_included = $false
            memory_dump_included = $false
            input_capture_included = $false
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
