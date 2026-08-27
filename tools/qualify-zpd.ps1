[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Matrix', 'Admission')]
    [string]$Action = 'Plan',
    [string]$StateRoot,
    [ValidateRange(1, 20)]
    [int]$ColdBoots = 10,
    [ValidateSet('fake', 'fast', 'strict')]
    [string]$AdmissionMode = 'fast',
    [ValidateSet('report_layout', 'pairwise_sentinel', 'relaxed_sentinel')]
    [string]$AdmissionPolicy = 'report_layout',
    [ValidateSet('none', 'pairwise_sentinel', 'relaxed_sentinel')]
    [string]$AdmissionFallback = 'pairwise_sentinel',
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

$matrix = @(
    [ordered]@{ mode = 'legacy'; policy = 'report_layout'; fallback = 'pairwise_sentinel'; label = 'legacy-existing' },
    [ordered]@{ mode = 'fake'; policy = 'report_layout'; fallback = 'pairwise_sentinel'; label = 'fake-layout' },
    [ordered]@{ mode = 'fast'; policy = 'report_layout'; fallback = 'pairwise_sentinel'; label = 'fast-layout' },
    [ordered]@{ mode = 'strict'; policy = 'report_layout'; fallback = 'pairwise_sentinel'; label = 'strict-layout' },
    [ordered]@{ mode = 'fast'; policy = 'pairwise_sentinel'; fallback = 'none'; label = 'fast-pairwise' },
    [ordered]@{ mode = 'fast'; policy = 'relaxed_sentinel'; fallback = 'none'; label = 'fast-relaxed' }
)
$runs = @(if ($Action -eq 'Admission') {
    @(1..$ColdBoots | ForEach-Object {
        [ordered]@{
            mode = $AdmissionMode
            policy = $AdmissionPolicy
            fallback = $AdmissionFallback
            label = "admission-$($_.ToString('00'))"
        }
    })
} else { $matrix })

if ($Action -eq 'Plan') {
    $plan = [ordered]@{
        schema = 'pinyon-shift.zpd-qualification-plan.v1'
        matrix = $matrix
        admission = [ordered]@{
            required_cold_boots = $ColdBoots
            mode = $AdmissionMode
            policy = $AdmissionPolicy
            fallback = $AdmissionFallback
        }
    }
    if ($Json) { $plan | ConvertTo-Json -Depth 6 -Compress } else { [pscustomobject]$plan }
    exit 0
}

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "The qualification requires an existing host config: $configPath"
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
    foreach ($run in $runs) {
        & (Join-Path $PSScriptRoot 'set-graphics-experiment.ps1') -Action Apply `
            -OcclusionQuery $run.mode -ZpdEndPolicy $run.policy `
            -ZpdEndFallback $run.fallback -StateRoot $resolvedStateRoot | Out-Null
        $startedUtc = [DateTime]::UtcNow
        $launchOutput = & $powershell -NoProfile -File `
            (Join-Path $PSScriptRoot 'launch-preview.ps1') `
            -StateRoot $resolvedStateRoot -Json 2>&1
        $exitCode = $LASTEXITCODE
        $launchResult = $launchOutput | Select-Object -Last 1 | ConvertFrom-Json
        if ($launchResult.exit_code -ne $exitCode) {
            throw "Launcher exit mismatch: process=$($launchResult.exit_code), host=$exitCode"
        }

        $intro = (Read-Host "[$($run.label)] Intro movie completed? [y/N]") -match '(?i)^y(?:es)?$'
        $controller = (Read-Host "[$($run.label)] Controller layout displayed? [y/N]") -match '(?i)^y(?:es)?$'
        $interactive = (Read-Host "[$($run.label)] First interactive menu/gameplay frame reached? [y/N]") -match '(?i)^y(?:es)?$'
        $visual = if ($run.mode -eq 'fast') {
            (Read-Host "[$($run.label)] Lighting/lens-flare occlusion looked correct? [y/N]") -match '(?i)^y(?:es)?$'
        } else { $true }

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
                -Pattern 'fatal|exception|assert|device removed' -CaseSensitive:$false).Count
        } else { 1 }
        $zpd = if ($summary -and $summary.zpd_counters) { $summary.zpd_counters } else { $null }
        $strictFallbacksBounded = $null -ne $zpd -and
            $zpd.zpd_retire_timeouts -le $zpd.zpd_strict_waits -and
            $zpd.zpd_watchdog_recoveries -le
                ($zpd.zpd_classified_begins + $zpd.zpd_classified_ends)
        $fallbacksHealthy = if ($null -eq $zpd) {
            $false
        } elseif ($run.mode -eq 'strict') {
            $strictFallbacksBounded
        } else {
            $zpd.zpd_retire_timeouts -eq 0 -and $zpd.zpd_watchdog_recoveries -eq 0
        }
        $countersHealthy = $null -ne $zpd -and
            $zpd.zpd_malformed_records -eq 0 -and
            $zpd.zpd_classified_orphaned_ends -eq 0 -and
            $zpd.zpd_classified_begins -eq $zpd.zpd_classified_ends -and
            $fallbacksHealthy
        $passed = $exitCode -eq 0 -and $intro -and $controller -and $interactive -and
            $visual -and $errorCount -eq 0 -and $countersHealthy
        $results.Add([ordered]@{
            label = $run.label
            mode = $run.mode
            policy = $run.policy
            fallback = $run.fallback
            started_utc = $startedUtc.ToString('o')
            markers = [ordered]@{
                intro_movie_complete = $intro
                controller_layout_displayed = $controller
                first_interactive_frame = $interactive
                visual_occlusion_correct = $visual
            }
            exit_code = $exitCode
            error_signatures = $errorCount
            performance_log = if ($perf) { $perf.Name } else { $null }
            event_log = if ($events) { $events.Name } else { $null }
            zpd_counters = $zpd
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
$reportPath = Join-Path $reportsPath "zpd-qualification-$stamp.json"
$report = [ordered]@{
    schema = 'pinyon-shift.zpd-qualification.v1'
    action = $Action.ToLowerInvariant()
    build = $build
    supported_dump = 'forza-horizon-usa-ms-2505-retail-base'
    required_cold_boots = if ($Action -eq 'Admission') { $ColdBoots } else { 1 }
    completed_runs = $results.Count
    passed = -not $failed -and $results.Count -eq $runs.Count
    original_config_restored = $true
    runs = $results
}
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
$output = [ordered]@{ passed = $report.passed; report = $reportPath; runs = $results.Count }
if ($Json) { $output | ConvertTo-Json -Compress } else { [pscustomobject]$output }
if (-not $report.passed) { exit 1 }
