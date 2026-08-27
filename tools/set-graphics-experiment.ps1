[CmdletBinding()]
param(
    [ValidateSet('Get', 'Apply', 'Reset', 'Restore')]
    [string]$Action = 'Get',
    [ValidateSet(4, 8, 16)]
    [int]$Anisotropy = 4,
    [ValidateSet('none', 'fxaa', 'fxaa_extreme')]
    [string]$PostEffect = 'none',
    [ValidateSet(1, 2, 3)]
    [int]$ResolutionScale = 1,
    [ValidateSet('custom', 'shipping_1x', 'experimental_2x', 'experimental_3x', 'accurate_showroom')]
    [string]$Preset = 'custom',
    [ValidateSet('none', 'fast', 'some', 'full')]
    [string]$ReadbackResolve = 'none',
    [ValidateSet('legacy', 'fake', 'fast', 'strict')]
    [string]$OcclusionQuery = 'legacy',
    [ValidateSet('report_layout', 'pairwise_sentinel', 'relaxed_sentinel')]
    [string]$ZpdEndPolicy = 'report_layout',
    [ValidateSet('none', 'pairwise_sentinel', 'relaxed_sentinel')]
    [string]$ZpdEndFallback = 'pairwise_sentinel',
    [ValidateSet(0, 30, 60)]
    [int]$PresentationFps = 60,
    [ValidateSet('true', 'false')]
    [string]$DisableMotionBlur = 'false',
    [ValidateSet('true', 'false')]
    [string]$DisableDepthOfField = 'false',
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
$configDirectory = Join-Path $resolvedStateRoot 'config'
$configPath = Join-Path $configDirectory 'pinyon_shift.toml'
$backupDirectory = Join-Path $configDirectory 'backups'

function Get-DefaultConfigText {
    @'
# Pinyon Shift host configuration.
# Schema 9 adds exact-hash FH1 post-processing switches.
pinyon_shift_config_schema = 9
input_backend = "sdl"
hid_mappings_file = "gamecontrollerdb.txt"
mnk_mode = true
keybind_a = "LMB,Space"
keybind_start = "Return"
d3d12_allow_variable_refresh_rate_and_tearing = false
vsync = true
host_present_fps_limit = 60
host_present_sleep_spin = true
pinyon_shift_stabilize_vehicle_presentation = false
pinyon_shift_skip_opening_movies = false
xma_relaxed_padding_admission = false
anisotropic_override = 3
swap_post_effect = "none"
disable_motion_blur = false
disable_depth_of_field = false
draw_resolution_scale_x = 1
draw_resolution_scale_y = 1
clear_memory_page_state = true
readback_resolve = "none"
readback_resolve_half_pixel_offset = false
readback_memexport = true
readback_memexport_fast = true
occlusion_query = "legacy"
zpd_end_policy = "report_layout"
zpd_end_fallback = "pairwise_sentinel"
'@
}

function New-ConfigBackup {
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return $null }
    [void](New-Item -ItemType Directory -Force -Path $backupDirectory)
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $destination = Join-Path $backupDirectory "pinyon_shift-$stamp.toml"
    Copy-Item -LiteralPath $configPath -Destination $destination
    $destination
}

function Get-SchemaVersion([string]$Text) {
    $match = [regex]::Match($Text,
        '(?m)^\s*pinyon_shift_config_schema\s*=\s*(?<value>[0-9]+)\s*(?:#.*)?$')
    if (-not $match.Success) { throw 'The host configuration has no schema version.' }
    [int]$match.Groups['value'].Value
}

function Set-TomlValue([string]$Text, [string]$Name, [string]$Value) {
    $pattern = '(?m)^\s*' + [regex]::Escape($Name) + '\s*=.*$'
    $replacement = "$Name = $Value"
    if ([regex]::IsMatch($Text, $pattern)) {
        return [regex]::Replace($Text, $pattern, $replacement, 1)
    }
    $trimmed = $Text.TrimEnd("`r", "`n")
    "$trimmed`r`n$replacement`r`n"
}

function Get-TomlValue([string]$Text, [string]$Name, [string]$Default) {
    $pattern = '(?m)^\s*' + [regex]::Escape($Name) + '\s*=\s*(?<value>[^#\r\n]+)'
    $match = [regex]::Match($Text, $pattern)
    if ($match.Success) { return $match.Groups['value'].Value.Trim().Trim('"') }
    $Default
}

function Write-Config([string]$Text) {
    [void](New-Item -ItemType Directory -Force -Path $configDirectory)
    $temporary = "$configPath.tmp"
    try {
        [IO.File]::WriteAllText($temporary, $Text.TrimEnd("`r", "`n") + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $configPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-SettingsResult([string]$Text, [string]$BackupPath, [string]$Operation) {
    $override = [int](Get-TomlValue $Text 'anisotropic_override' '3')
    $anisotropyValue = switch ($override) { 3 { 4 } 4 { 8 } 5 { 16 } default { 4 } }
    $resolutionScale = [int](Get-TomlValue $Text 'draw_resolution_scale_x' '1')
    $readbackResolve = Get-TomlValue $Text 'readback_resolve' 'none'
    $halfPixel = (Get-TomlValue $Text 'readback_resolve_half_pixel_offset' 'false') -eq 'true'
    $clearPageState = (Get-TomlValue $Text 'clear_memory_page_state' 'true') -eq 'true'
    $memexport = (Get-TomlValue $Text 'readback_memexport' 'true') -eq 'true'
    $memexportFast = (Get-TomlValue $Text 'readback_memexport_fast' 'true') -eq 'true'
    $vsyncEnabled = (Get-TomlValue $Text 'vsync' 'true') -eq 'true'
    $presentationFps = [int](Get-TomlValue $Text 'host_present_fps_limit' '60')
    $presetName = if ($clearPageState -and $readbackResolve -eq 'full') {
        'accurate_showroom'
    } elseif ($clearPageState -and $resolutionScale -eq 2 -and
        $readbackResolve -eq 'fast' -and $halfPixel) {
        'experimental_2x'
    } elseif ($clearPageState -and $resolutionScale -eq 3 -and
        $readbackResolve -eq 'fast' -and $halfPixel) {
        'experimental_3x'
    } elseif ($clearPageState -and $resolutionScale -eq 1 -and
        $readbackResolve -eq 'none' -and -not $halfPixel -and $memexport -and
        $memexportFast -and $vsyncEnabled) {
        'shipping_1x'
    } else {
        'custom'
    }
    [ordered]@{
        schema = 'pinyon-shift.graphics-settings.v2'
        operation = $Operation.ToLowerInvariant()
        config_path = $configPath
        backup_path = $BackupPath
        settings = [ordered]@{
            anisotropy = $anisotropyValue
            post_effect = Get-TomlValue $Text 'swap_post_effect' 'none'
            disable_motion_blur = (Get-TomlValue $Text 'disable_motion_blur' 'false') -eq 'true'
            disable_depth_of_field = (Get-TomlValue $Text 'disable_depth_of_field' 'false') -eq 'true'
            preset = $presetName
            resolution_scale = $resolutionScale
            readback_resolve = $readbackResolve
            readback_resolve_half_pixel_offset = $halfPixel
            clear_memory_page_state = $clearPageState
            readback_memexport = $memexport
            readback_memexport_fast = $memexportFast
            vsync = $vsyncEnabled
            host_present_fps_limit = $presentationFps
            host_present_sleep_spin =
                (Get-TomlValue $Text 'host_present_sleep_spin' 'true') -eq 'true'
            occlusion_query = Get-TomlValue $Text 'occlusion_query' 'legacy'
            zpd_end_policy = Get-TomlValue $Text 'zpd_end_policy' 'report_layout'
            zpd_end_fallback = Get-TomlValue $Text 'zpd_end_fallback' 'pairwise_sentinel'
        }
        restart_required = $Operation -ne 'Get'
    }
}

[void](New-Item -ItemType Directory -Force -Path $configDirectory)
$backup = $null
switch ($Action) {
    'Get' {
        $text = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            Get-Content -LiteralPath $configPath -Raw
        } else { Get-DefaultConfigText }
        $schema = Get-SchemaVersion $text
        if ($schema -notin @(1, 2, 3, 4, 5, 6, 7, 8, 9)) { throw "Unsupported host configuration schema: $schema" }
    }
    'Reset' {
        $backup = New-ConfigBackup
        $text = Get-DefaultConfigText
        Write-Config $text
    }
    'Restore' {
        if (-not (Test-Path -LiteralPath $backupDirectory -PathType Container)) {
            throw 'No runtime-settings backup is available.'
        }
        $source = Get-ChildItem -LiteralPath $backupDirectory -Filter 'pinyon_shift-*.toml' -File |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -eq $source) { throw 'No runtime-settings backup is available.' }
        $backup = New-ConfigBackup
        $text = Get-Content -LiteralPath $source.FullName -Raw
        $schema = Get-SchemaVersion $text
        if ($schema -notin @(1, 2, 3, 4, 5, 6, 7, 8, 9)) { throw "Backup uses unsupported schema: $schema" }
        Write-Config $text
    }
    'Apply' {
        $text = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            Get-Content -LiteralPath $configPath -Raw
        } else { Get-DefaultConfigText }
        $schema = Get-SchemaVersion $text
        if ($schema -notin @(1, 2, 3, 4, 5, 6, 7, 8, 9)) { throw "Unsupported host configuration schema: $schema" }
        $backup = New-ConfigBackup
        $text = Set-TomlValue $text 'pinyon_shift_config_schema' '9'
        if (-not [regex]::IsMatch($text, '(?m)^\s*xma_relaxed_padding_admission\s*=')) {
            $text = Set-TomlValue $text 'xma_relaxed_padding_admission' 'false'
        }
        if (-not [regex]::IsMatch($text, '(?m)^\s*occlusion_query\s*=')) {
            $text = Set-TomlValue $text 'occlusion_query' '"legacy"'
        }
        $effectiveResolution = switch ($Preset) {
            'shipping_1x' { 1 }
            'experimental_2x' { 2 }
            'experimental_3x' { 3 }
            'accurate_showroom' { 1 }
            default { $ResolutionScale }
        }
        $effectiveReadback = switch ($Preset) {
            'shipping_1x' { 'none' }
            'experimental_2x' { 'fast' }
            'experimental_3x' { 'fast' }
            'accurate_showroom' { 'full' }
            default { $ReadbackResolve }
        }
        $effectiveHalfPixel = $Preset -in @('experimental_2x', 'experimental_3x') -or
            ($Preset -eq 'custom' -and $effectiveResolution -gt 1 -and
                $effectiveReadback -ne 'none')
        $effectiveHalfPixelText = if ($effectiveHalfPixel) { 'true' } else { 'false' }
        $override = switch ($Anisotropy) { 4 { 3 } 8 { 4 } 16 { 5 } }
        $text = Set-TomlValue $text 'anisotropic_override' ([string]$override)
        $text = Set-TomlValue $text 'swap_post_effect' ('"' + $PostEffect + '"')
        $text = Set-TomlValue $text 'disable_motion_blur' $DisableMotionBlur
        $text = Set-TomlValue $text 'disable_depth_of_field' $DisableDepthOfField
        $text = Set-TomlValue $text 'draw_resolution_scale_x' ([string]$effectiveResolution)
        $text = Set-TomlValue $text 'draw_resolution_scale_y' ([string]$effectiveResolution)
        $text = Set-TomlValue $text 'vsync' 'true'
        $text = Set-TomlValue $text 'host_present_fps_limit' ([string]$PresentationFps)
        $text = Set-TomlValue $text 'host_present_sleep_spin' 'true'
        $text = Set-TomlValue $text 'clear_memory_page_state' 'true'
        $text = Set-TomlValue $text 'readback_resolve' ('"' + $effectiveReadback + '"')
        $text = Set-TomlValue $text 'readback_resolve_half_pixel_offset' $effectiveHalfPixelText
        $text = Set-TomlValue $text 'readback_memexport' 'true'
        $text = Set-TomlValue $text 'readback_memexport_fast' 'true'
        $text = Set-TomlValue $text 'occlusion_query' ('"' + $OcclusionQuery + '"')
        $text = Set-TomlValue $text 'zpd_end_policy' ('"' + $ZpdEndPolicy + '"')
        $text = Set-TomlValue $text 'zpd_end_fallback' ('"' + $ZpdEndFallback + '"')
        Write-Config $text
    }
}

$result = Get-SettingsResult $text $backup $Action
if ($Json) { $result | ConvertTo-Json -Depth 5 -Compress } else { [pscustomobject]$result }
