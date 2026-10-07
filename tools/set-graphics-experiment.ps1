[CmdletBinding()]
param(
    [ValidateSet('Get', 'Apply', 'Reset', 'Restore')]
    [string]$Action = 'Get',
    [ValidateSet(4, 8, 16)]
    [int]$Anisotropy = 4,
    [ValidateSet('none', 'fxaa', 'fxaa_extreme')]
    [string]$PostEffect = 'none',
    [ValidateSet(1, 2, 3, 4)]
    [int]$ResolutionScale = 1,
    [ValidateSet('vulkan')]
    [string]$GraphicsApi = 'vulkan',
    [ValidateSet('bilinear', 'cas', 'fsr')]
    [string]$OutputScaling = 'bilinear',
    [ValidateSet('true', 'false')]
    [string]$TreasureMap = 'true',
    [ValidateSet('custom', 'shipping_1x', 'experimental_2x', 'experimental_3x')]
    [string]$Preset = 'custom',
    [ValidateSet(0, 30, 60, 120, 240)]
    [int]$PresentationFps = 0,
    [ValidateRange(0, 240)]
    [int]$RenderFps = 0,
    [ValidateSet('true', 'false')]
    [string]$DisableBloom = 'true',
    [ValidateSet('true', 'false')]
    [string]$DisableMotionBlur = 'true',
    [ValidateSet('true', 'false')]
    [string]$DisableDepthOfField = 'true',
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
. (Join-Path $PSScriptRoot 'host-config.ps1')

function Get-DefaultConfigText {
    @'
# Pinyon Shift host configuration.
# Schema 28 supports only Vulkan with the split GPU commands thread; schema 26
# stops re-uploading CPU-written memory every frame; schema 25 keeps one
# occlusion-query path; schema 24 retired the renderer choice.
pinyon_shift_config_schema = 28
input_backend = "sdl"
hid_mappings_file = "gamecontrollerdb.txt"
mnk_mode = true
keybind_a = "LMB,Space"
keybind_start = "Return"
d3d12_allow_variable_refresh_rate_and_tearing = false
gpu_backend = "vulkan"
gpu_record_thread = true
vsync = true
host_present_fps_limit = 0
host_present_sleep_spin = true
pinyon_shift_stabilize_vehicle_presentation = false
pinyon_shift_skip_opening_movies = false
pinyon_shift_fh1_render_fps_limit = 0
pinyon_shift_fh1_source_presentation = true
xma_relaxed_padding_admission = false
anisotropic_override = 3
swap_post_effect = "none"
disable_bloom = true
disable_motion_blur = true
disable_depth_of_field = true
fh1_msaa_single_sample = true
draw_resolution_scale_x = 1
draw_resolution_scale_y = 1
clear_memory_page_state = false
'@
}

# Settings a config file may still carry from an earlier release. Apply writes
# the current schema, so the game's own migration never sees the file again:
# drop every setting that migration retires (src/pinyon_shift_app.cpp).
$retiredSettings = @(
    'pinyon_shift_fh1_guest_vblank_hz',
    'pinyon_shift_native_renderer_texture_bridge',
    'pinyon_shift_native_renderer',
    'pinyon_shift_native_renderer_sky_horizon_suppression',
    'pinyon_shift_native_renderer_census',
    'pinyon_shift_fh1_native_v4',
    'readback_resolve_half_pixel_offset',
    'readback_memexport',
    'readback_memexport_fast',
    'fh1_renderer',
    'fh1_native_shadow',
    'fh1_native_shadow_dump_dir',
    'fh1_native_shadow_dump_frames',
    'fh1_native_shadow_verify',
    'fh1_native_shadow_verify_draws',
    'fh1_discovery_sampling',
    'fh1_owned_depth_clear',
    'fh1_owned_depth_tile_clear',
    'fh1_native_reflection_mips',
    'fh1_mip_decode_probe',
    'fh1_native_ui_boundary_probe',
    'fh1_glow_probe',
    'fh1_recycle_geometry_buffers',
    'fh1_contain_geometry_windows',
    'fh1_cache_geometry_rejections',
    'fh1_geometry_cache_mb',
    'native_stencil_value_output',
    'native_stencil_value_output_d3d12_intel',
    'pinyon_shift_native_race',
    'pinyon_shift_native_race_capture_start_frame',
    'pinyon_shift_native_ui_live',
    'pinyon_shift_native_ui_replay_source_frame',
    'pinyon_shift_native_ui_scene_probe',
    'pinyon_shift_native_ui_shadow_start_frame',
    'pinyon_shift_native_ui_clear_probe',
    'pinyon_shift_native_output_clear_probe',
    'pinyon_shift_native_scene_clear_probe',
    'pinyon_shift_native_scene_triangle_probe',
    'pinyon_shift_native_small_target_probe',
    'pinyon_shift_native_track_probe',
    'pinyon_shift_native_ordered_live_probe',
    'pinyon_shift_fh1_clear_producer_trace',
    'pinyon_shift_fh1_scene_dump',
    'pinyon_shift_snr01_trace_following_frame',
    'pinyon_shift_snr01_trace_resident_packet_writers',
    'pinyon_shift_snr01_trace_source_frame',
    'pinyon_shift_snr01_watch_packet_pages',
    'pinyon_shift_snr02_item_payload_probe',
    'pinyon_shift_snr02_trace_first_rebuild_after_frame',
    'pinyon_shift_snr02_trace_view_call',
    'pinyon_shift_snr02_track_payload_probe',
    'pinyon_shift_snr03_probe_following_frame',
    'pinyon_shift_snr03_probe_frame',
    'pinyon_shift_snr04_live_continuous',
    'pinyon_shift_snr04_live_handoff',
    'pinyon_shift_snr04_live_source_frame',
    'pinyon_shift_snr04_live_worker',
    'pinyon_shift_snr_m02_trace_source_frame',
    'occlusion_query',
    'zpd_end_policy',
    'zpd_end_fallback'
)

function Get-SchemaVersion([string]$Text) {
    $match = [regex]::Match($Text,
        '(?m)^\s*pinyon_shift_config_schema\s*=\s*(?<value>[0-9]+)\s*(?:#.*)?$')
    if (-not $match.Success) { throw 'The host configuration has no schema version.' }
    [int]$match.Groups['value'].Value
}

function Get-SettingsResult([string]$Text, [string]$BackupPath, [string]$Operation) {
    $override = [int](Get-TomlValue $Text 'anisotropic_override' '3')
    $anisotropyValue = switch ($override) { 3 { 4 } 4 { 8 } 5 { 16 } default { 4 } }
    $resolutionScale = [int](Get-TomlValue $Text 'draw_resolution_scale_x' '1')
    $clearPageState = (Get-TomlValue $Text 'clear_memory_page_state' 'false') -eq 'true'
    $vsyncEnabled = (Get-TomlValue $Text 'vsync' 'true') -eq 'true'
    $presentationFps = [int](Get-TomlValue $Text 'host_present_fps_limit' '0')
    $renderFps = [int](Get-TomlValue $Text 'pinyon_shift_fh1_render_fps_limit' '0')
    # Player settings use Vulkan; schema 28 migrates legacy backend selections.
    $graphicsApi = 'vulkan'
    $presetName = if ($resolutionScale -eq 2) {
        'experimental_2x'
    } elseif ($resolutionScale -eq 3) {
        'experimental_3x'
    } elseif ($resolutionScale -eq 1 -and $vsyncEnabled) {
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
            disable_bloom = (Get-TomlValue $Text 'disable_bloom' 'true') -eq 'true'
            disable_motion_blur = (Get-TomlValue $Text 'disable_motion_blur' 'true') -eq 'true'
            disable_depth_of_field = (Get-TomlValue $Text 'disable_depth_of_field' 'true') -eq 'true'
            preset = $presetName
            resolution_scale = $resolutionScale
            graphics_api = $graphicsApi
            output_scaling = (Get-TomlValue $Text 'present_effect' '"bilinear"').Trim('"').ToLowerInvariant()
            # Where the image lands, for the launcher's resolution line.
            fullscreen = (Get-TomlValue $Text 'fullscreen' 'true') -eq 'true'
            monitor = [int](Get-TomlValue $Text 'monitor' '0')
            window_width = [int](Get-TomlValue $Text 'window_width' '0')
            window_height = [int](Get-TomlValue $Text 'window_height' '0')
            letterbox = (Get-TomlValue $Text 'present_letterbox' 'true') -eq 'true'
            # The game turns the Treasure Map on unless the file says false.
            treasure_map = (Get-TomlValue $Text 'pinyon_shift_dlc_treasure_map' 'true') -eq 'true'
            clear_memory_page_state = $clearPageState
            vsync = $vsyncEnabled
            host_present_fps_limit = $presentationFps
            fh1_render_fps_limit = $renderFps
            host_present_sleep_spin =
                (Get-TomlValue $Text 'host_present_sleep_spin' 'true') -eq 'true'
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
        if ($schema -lt 1 -or $schema -gt 28) { throw "Unsupported host configuration schema: $schema" }
    }
    'Reset' {
        $backup = New-HostConfigBackup $configPath
        $text = Get-DefaultConfigText
        Write-HostConfig $configPath $text
    }
    'Restore' {
        if (-not (Test-Path -LiteralPath $backupDirectory -PathType Container)) {
            throw 'No runtime-settings backup is available.'
        }
        $source = Get-ChildItem -LiteralPath $backupDirectory -Filter 'pinyon_shift-*.toml' -File |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -eq $source) { throw 'No runtime-settings backup is available.' }
        $backup = New-HostConfigBackup $configPath
        $text = Get-Content -LiteralPath $source.FullName -Raw
        $schema = Get-SchemaVersion $text
        if ($schema -lt 1 -or $schema -gt 28) { throw "Backup uses unsupported schema: $schema" }
        Write-HostConfig $configPath $text
    }
    'Apply' {
        $text = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            Get-Content -LiteralPath $configPath -Raw
        } else { Get-DefaultConfigText }
        $schema = Get-SchemaVersion $text
        if ($schema -lt 1 -or $schema -gt 28) { throw "Unsupported host configuration schema: $schema" }
        $backup = New-HostConfigBackup $configPath
        # The retired guest vblank rate became the render limit, which the
        # replacement defaults to following the display.
        $hadLegacyVblank = [regex]::IsMatch($text, '(?m)^[ \t]*pinyon_shift_fh1_guest_vblank_hz[ \t]*=')
        foreach ($retired in $retiredSettings) {
            $text = Remove-TomlValue $text $retired
        }
        # readback_resolve is a developer setting; only launchers before
        # schema 24 wrote it for players (src/pinyon_shift_app.cpp).
        if ($schema -lt 24) { $text = Remove-TomlValue $text 'readback_resolve' }
        # Schema 26 turned clear_memory_page_state off (src/pinyon_shift_app.cpp).
        if ($schema -lt 26) { $text = Set-TomlValue $text 'clear_memory_page_state' 'false' }
        # Schema 28 makes Vulkan the only supported player backend.
        $text = Set-TomlValue $text 'gpu_backend' '"vulkan"'
        $text = Set-TomlValue $text 'gpu_record_thread' 'true'
        $text = Set-TomlValue $text 'pinyon_shift_config_schema' '28'
        $text = Set-TomlValue $text 'pinyon_shift_fh1_source_presentation' 'true'
        if (-not [regex]::IsMatch($text, '(?m)^[ \t]*xma_relaxed_padding_admission[ \t]*=')) {
            $text = Set-TomlValue $text 'xma_relaxed_padding_admission' 'false'
        }
        # Only the settings passed are written: the in-game settings screen
        # edits the same file, and saving here must not undo its choices.
        $bound = $PSBoundParameters
        $effectiveResolution = switch ($Preset) {
            'shipping_1x' { 1 }
            'experimental_2x' { 2 }
            'experimental_3x' { 3 }
            default { $null }
        }
        if ($null -eq $effectiveResolution -and $bound.ContainsKey('ResolutionScale')) {
            $effectiveResolution = $ResolutionScale
        }
        if ($null -ne $effectiveResolution) {
            $text = Set-TomlValue $text 'draw_resolution_scale_x' ([string]$effectiveResolution)
            $text = Set-TomlValue $text 'draw_resolution_scale_y' ([string]$effectiveResolution)
        }
        if ($bound.ContainsKey('TreasureMap')) {
            $text = Set-TomlValue $text 'pinyon_shift_dlc_treasure_map' $TreasureMap
        }
        if ($bound.ContainsKey('OutputScaling')) {
            $text = Set-TomlValue $text 'present_effect' ('"' + $OutputScaling + '"')
        }
        if ($bound.ContainsKey('Anisotropy')) {
            $override = switch ($Anisotropy) { 4 { 3 } 8 { 4 } 16 { 5 } }
            $text = Set-TomlValue $text 'anisotropic_override' ([string]$override)
        }
        if ($bound.ContainsKey('PostEffect')) {
            $text = Set-TomlValue $text 'swap_post_effect' ('"' + $PostEffect + '"')
        }
        if ($bound.ContainsKey('DisableBloom')) {
            $text = Set-TomlValue $text 'disable_bloom' $DisableBloom
        }
        if ($bound.ContainsKey('DisableMotionBlur')) {
            $text = Set-TomlValue $text 'disable_motion_blur' $DisableMotionBlur
        }
        if ($bound.ContainsKey('DisableDepthOfField')) {
            $text = Set-TomlValue $text 'disable_depth_of_field' $DisableDepthOfField
        }
        if ($bound.ContainsKey('PresentationFps')) {
            $text = Set-TomlValue $text 'host_present_fps_limit' ([string]$PresentationFps)
        }
        if ($bound.ContainsKey('RenderFps') -or $hadLegacyVblank) {
            $text = Set-TomlValue $text 'pinyon_shift_fh1_render_fps_limit' ([string]$RenderFps)
        }
        $text = Set-TomlValue $text 'host_present_sleep_spin' 'true'
        Write-HostConfig $configPath $text
    }
}

$result = Get-SettingsResult $text $backup $Action
if ($Json) { $result | ConvertTo-Json -Depth 5 -Compress } else { [pscustomobject]$result }
