[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$StateRoot,
    [string]$GameRoot,
    [string]$BuildDirectory,
    [switch]$JsonEvents
)

# Vulkan translates shaders and creates pipelines as the game runs, and keeps
# them for later launches: its shader and pipeline storage, the Vulkan
# pipeline cache and the driver's own shader cache. A first launch without
# any of them stalls for seconds, inside races too (DR-1.3: 13 s of frame time
# over 16.7 ms on the race route with an empty driver cache, single frames up
# to 1.35 s). So before the first start this plays the shader preparation
# route once, hidden, with the player's settings, which fills the driver's
# cache, and keeps the storage it wrote. Later launches recreate the stored
# pipelines while the game starts. A failure is a warning: the game still
# plays, it only stutters the first time.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$cache = Join-Path $StateRoot 'cache'
$config = Join-Path $StateRoot 'config/pinyon_shift.toml'

$work = Resolve-PinyonLocalPath -RelativePath ('.local/native-renderer/vulkan-preparation-' + [Guid]::NewGuid().ToString('N'))
$routeState = Join-Path $work 'state'
[void][IO.Directory]::CreateDirectory((Join-Path $routeState 'config'))
if (Test-Path -LiteralPath $config) { Copy-Item -LiteralPath $config -Destination (Join-Path $routeState 'config/pinyon_shift.toml') }
# The route's start builds the ahead-of-time pipelines too, so the driver's
# cache holds them before the player's first start.
$pipelines = Join-Path $cache 'shaders/shareable/4D5309C9.fbo.aot.xpso'
if (Test-Path -LiteralPath $pipelines) {
    $shareable = Join-Path $routeState 'cache/shaders/shareable'
    [void][IO.Directory]::CreateDirectory($shareable)
    Copy-Item -LiteralPath $pipelines -Destination $shareable
}

function Skip-Preparation([string]$Reason) {
    Write-PinyonEvent shaders 100 "Vulkan shader preparation was skipped: $Reason The first race may stutter while shaders are prepared. Details: $work" -JsonEvents:$JsonEvents
}

Write-PinyonEvent shaders 0 'Preparing Vulkan shaders: playing the opening once, hidden. This takes a few minutes, once.' -JsonEvents:$JsonEvents
$arguments = @{
    RenderTestScript = (Join-Path $root 'config/render-tests/fh1-shader-preparation.fh1test')
    RenderTestOutput = (Join-Path $work 'output'); RenderTestIncludeOpeningMovies = $true
    StateRoot = $routeState; Hidden = $true; Json = $true
}
if ($GameRoot) { $arguments.GameRoot = $GameRoot }
if ($BuildDirectory) { $arguments.BuildDirectory = $BuildDirectory }
try { $launch = & (Join-Path $PSScriptRoot 'launch-preview.ps1') @arguments | ConvertFrom-Json }
catch { Skip-Preparation "the preparation route did not finish ($($_.Exception.Message))."; return }
$events = @(Get-ChildItem -LiteralPath (Join-Path $routeState 'logs') -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
    ForEach-Object { Get-Content -LiteralPath $_.FullName } | ForEach-Object { $_ | ConvertFrom-Json })
if ($launch.result -ne 'normal-exit' -or @($events | Where-Object event -eq 'fh1.render_test.complete').Count -ne 1) {
    Skip-Preparation "the preparation route did not complete (result $($launch.result))."
    return
}

# Keep the storage the route wrote. Never replace storage the player already
# has: it may hold more than the route reached.
$copied = 0
foreach ($set in @(
    @{ From = 'cache/shaders/shareable'; Patterns = @('*.xsh', '*.vk.xpso') },
    @{ From = 'cache/shaders'; Patterns = @('*.vkpipelinecache.*.bin') }
)) {
    $destination = Join-Path $StateRoot $set.From
    foreach ($pattern in $set.Patterns) {
        foreach ($file in @(Get-ChildItem -LiteralPath (Join-Path $routeState $set.From) -Filter $pattern -File -ErrorAction SilentlyContinue)) {
            $target = Join-Path $destination $file.Name
            if (Test-Path -LiteralPath $target) { continue }
            [void][IO.Directory]::CreateDirectory($destination)
            $temporary = "$target.$([Guid]::NewGuid().ToString('N')).tmp"
            Copy-Item -LiteralPath $file.FullName -Destination $temporary
            Move-Item -LiteralPath $temporary -Destination $target
            $copied++
        }
    }
}
if (-not @(Get-ChildItem -LiteralPath (Join-Path $cache 'shaders/shareable') -Filter '*.vk.xpso' -File -ErrorAction SilentlyContinue).Count) {
    Skip-Preparation 'the preparation route wrote no Vulkan pipeline storage.'
    return
}
Remove-Item -LiteralPath $work -Recurse -Force
Write-PinyonEvent shaders 100 "Vulkan shaders are prepared ($copied storage files kept)." -JsonEvents:$JsonEvents
