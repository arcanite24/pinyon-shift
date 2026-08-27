[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Run')]
    [string]$Action = 'Plan',
    [string]$StateRoot,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$resolvedStateRoot = if ($StateRoot) {
    [IO.Path]::GetFullPath($StateRoot)
} else {
    Join-Path $repoRoot '.local/preview'
}
$configPath = Join-Path $resolvedStateRoot 'config/pinyon_shift.toml'
$logsPath = Join-Path $resolvedStateRoot 'logs'
$reportsPath = Join-Path $resolvedStateRoot 'reports'
$buildPath = Join-Path $repoRoot 'out/build/win-amd64-release/pinyon_shift_build.json'
$powershell = (Get-Process -Id $PID).Path

$profiles = @(
    [ordered]@{
        preset = 'shipping_1x'
        label = 'shipping-1x'
        markers = @('front_end', 'open_world_day', 'open_world_night', 'race', 'rewind')
    },
    [ordered]@{
        preset = 'experimental_2x'
        label = 'experimental-2x'
        markers = @('garage', 'autoshow', 'livery', 'colored_artifacts_absent')
    },
    [ordered]@{
        preset = 'accurate_showroom'
        label = 'accurate-showroom'
        markers = @('garage', 'autoshow', 'livery', 'assets_correct')
    }
)

if ($Action -eq 'Plan') {
    $plan = [ordered]@{
        schema = 'pinyon-shift.resolve-qualification-plan.v1'
        profiles = $profiles
        restore_original_config = $true
        candidate_scenes = @(
            'front-end', 'garage', 'autoshow', 'livery',
            'open-world-day', 'open-world-night', 'race', 'rewind'
        )
    }
    if ($Json) { $plan | ConvertTo-Json -Depth 6 -Compress } else { [pscustomobject]$plan }
    exit 0
}

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Resolve qualification requires an existing host config: $configPath"
}
if (-not (Test-Path -LiteralPath $buildPath -PathType Leaf)) {
    throw 'Build provenance is missing. Run tools/build-preview.ps1 first.'
}
if (Get-Process -Name pinyon_shift -ErrorAction SilentlyContinue) {
    throw 'Pinyon Shift is already running.'
}
$save = Get-ChildItem -LiteralPath (Join-Path $resolvedStateRoot 'user') -Recurse `
    -Filter ForzaProfile -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Directory.Name -eq 'ForzaProfile' } | Select-Object -First 1
if ($null -eq $save) { throw 'The AppData-backed ForzaProfile save was not found.' }

$originalConfig = Get-Content -LiteralPath $configPath -Raw
$build = Get-Content -LiteralPath $buildPath -Raw | ConvertFrom-Json
$results = [Collections.Generic.List[object]]::new()
$failed = $false
try {
    foreach ($profile in $profiles) {
        & (Join-Path $PSScriptRoot 'set-graphics-experiment.ps1') -Action Apply `
            -Preset $profile.preset -StateRoot $resolvedStateRoot | Out-Null
        $startedUtc = [DateTime]::UtcNow
        $launchOutput = & $powershell -NoProfile -File `
            (Join-Path $PSScriptRoot 'launch-preview.ps1') `
            -StateRoot $resolvedStateRoot -Json 2>&1
        $exitCode = $LASTEXITCODE
        $launchResult = $launchOutput | Select-Object -Last 1 | ConvertFrom-Json
        if ($launchResult.exit_code -ne $exitCode) {
            throw "Launcher exit mismatch: process=$($launchResult.exit_code), host=$exitCode"
        }

        $markers = [ordered]@{}
        foreach ($marker in $profile.markers) {
            $label = $marker.Replace('_', ' ')
            $markers[$marker] = ((Read-Host "[$($profile.label)] $label verified? [y/N]") `
                -match '(?i)^y(?:es)?$')
        }

        $perf = Get-ChildItem -LiteralPath $logsPath -Filter '*.perf.csv' -File |
            Where-Object { $_.LastWriteTimeUtc -ge $startedUtc.AddSeconds(-2) } |
            Sort-Object LastWriteTimeUtc | Select-Object -Last 1
        $events = Get-ChildItem -LiteralPath $logsPath -Filter '*.jsonl' -File |
            Where-Object { $_.LastWriteTimeUtc -ge $startedUtc.AddSeconds(-2) } |
            Sort-Object LastWriteTimeUtc | Select-Object -Last 1
        $summary = if ($perf) {
            & python (Join-Path $PSScriptRoot 'summarize-performance.py') $perf.FullName |
                ConvertFrom-Json
        } else { $null }
        $errorCount = if ($events) {
            @(Select-String -LiteralPath $events.FullName `
                -Pattern 'fatal|error|exception|assert|device.?removed' -CaseSensitive:$false).Count
        } else { 1 }
        $resolve = if ($summary -and $summary.resolve_readback_counters) {
            $summary.resolve_readback_counters
        } else { $null }
        $countersHealthy = if ($null -eq $resolve) {
            $false
        } elseif ($profile.preset -eq 'shipping_1x') {
            $resolve.resolve_readback_requests -eq 0 -and
                $resolve.resolve_readback_bytes -eq 0 -and
                $resolve.resolve_readback_full_waits -eq 0
        } elseif ($profile.preset -eq 'experimental_2x') {
            $resolve.resolve_readback_requests -gt 0 -and
                $resolve.resolve_readback_bytes -gt 0 -and
                $resolve.resolve_readback_fast_copies -gt 0
        } else {
            $resolve.resolve_readback_requests -gt 0 -and
                $resolve.resolve_readback_bytes -gt 0 -and
                $resolve.resolve_readback_full_waits -gt 0 -and
                $resolve.resolve_readback_wait_time_ns -gt 0
        }
        $markersHealthy = @($markers.Values | Where-Object { -not $_ }).Count -eq 0
        $passed = $exitCode -eq 0 -and $markersHealthy -and $errorCount -eq 0 -and
            $countersHealthy
        $results.Add([ordered]@{
            label = $profile.label
            preset = $profile.preset
            started_utc = $startedUtc.ToString('o')
            markers = $markers
            exit_code = $exitCode
            error_signatures = $errorCount
            performance_log = if ($perf) { $perf.Name } else { $null }
            event_log = if ($events) { $events.Name } else { $null }
            frame_summary = if ($summary) { $summary.frames } else { $null }
            resolve_readback_counters = $resolve
            passed = $passed
        })
        if (-not $passed) {
            $failed = $true
            break
        }
    }
}
finally {
    [IO.File]::WriteAllText($configPath, $originalConfig,
        [Text.UTF8Encoding]::new($false))
}

[void](New-Item -ItemType Directory -Force -Path $reportsPath)
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$reportPath = Join-Path $reportsPath "resolve-qualification-$stamp.json"
$report = [ordered]@{
    schema = 'pinyon-shift.resolve-qualification.v1'
    build = $build
    supported_dump = 'forza-horizon-usa-ms-2505-retail-base'
    completed_runs = $results.Count
    passed = -not $failed -and $results.Count -eq $profiles.Count
    original_config_restored = $true
    runs = $results
}
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
$output = [ordered]@{ passed = $report.passed; report = $reportPath; runs = $results.Count }
if ($Json) { $output | ConvertTo-Json -Compress } else { [pscustomobject]$output }
if (-not $report.passed) { exit 1 }
