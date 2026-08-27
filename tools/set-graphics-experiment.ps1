[CmdletBinding()]
param(
    [ValidateSet('Get', 'Apply', 'Reset', 'Restore')]
    [string]$Action = 'Get',
    [ValidateSet(4, 8, 16)]
    [int]$Anisotropy = 4,
    [ValidateSet('none', 'fxaa', 'fxaa_extreme')]
    [string]$PostEffect = 'none',
    [ValidateSet(1, 2)]
    [int]$ResolutionScale = 1,
    [ValidateSet('legacy', 'fake', 'fast', 'strict')]
    [string]$OcclusionQuery = 'legacy',
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
# Schema 6 adds conservative ZPD lifecycle selection.
pinyon_shift_config_schema = 6
input_backend = "sdl"
hid_mappings_file = "gamecontrollerdb.txt"
mnk_mode = true
keybind_a = "LMB,Space"
keybind_start = "Return"
d3d12_allow_variable_refresh_rate_and_tearing = false
pinyon_shift_stabilize_vehicle_presentation = false
pinyon_shift_skip_opening_movies = false
xma_relaxed_padding_admission = false
anisotropic_override = 3
swap_post_effect = "none"
draw_resolution_scale_x = 1
draw_resolution_scale_y = 1
occlusion_query = "legacy"
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
    [ordered]@{
        schema = 'pinyon-shift.graphics-settings.v1'
        operation = $Operation.ToLowerInvariant()
        config_path = $configPath
        backup_path = $BackupPath
        settings = [ordered]@{
            anisotropy = $anisotropyValue
            post_effect = Get-TomlValue $Text 'swap_post_effect' 'none'
            resolution_scale = [int](Get-TomlValue $Text 'draw_resolution_scale_x' '1')
            occlusion_query = Get-TomlValue $Text 'occlusion_query' 'legacy'
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
        if ($schema -notin @(1, 2, 3, 4, 5, 6)) { throw "Unsupported host configuration schema: $schema" }
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
        if ($schema -notin @(1, 2, 3, 4, 5, 6)) { throw "Backup uses unsupported schema: $schema" }
        Write-Config $text
    }
    'Apply' {
        $text = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            Get-Content -LiteralPath $configPath -Raw
        } else { Get-DefaultConfigText }
        $schema = Get-SchemaVersion $text
        if ($schema -notin @(1, 2, 3, 4, 5, 6)) { throw "Unsupported host configuration schema: $schema" }
        $backup = New-ConfigBackup
        $text = Set-TomlValue $text 'pinyon_shift_config_schema' '6'
        if (-not [regex]::IsMatch($text, '(?m)^\s*xma_relaxed_padding_admission\s*=')) {
            $text = Set-TomlValue $text 'xma_relaxed_padding_admission' 'false'
        }
        if (-not [regex]::IsMatch($text, '(?m)^\s*occlusion_query\s*=')) {
            $text = Set-TomlValue $text 'occlusion_query' '"legacy"'
        }
        $override = switch ($Anisotropy) { 4 { 3 } 8 { 4 } 16 { 5 } }
        $text = Set-TomlValue $text 'anisotropic_override' ([string]$override)
        $text = Set-TomlValue $text 'swap_post_effect' ('"' + $PostEffect + '"')
        $text = Set-TomlValue $text 'draw_resolution_scale_x' ([string]$ResolutionScale)
        $text = Set-TomlValue $text 'draw_resolution_scale_y' ([string]$ResolutionScale)
        $text = Set-TomlValue $text 'occlusion_query' ('"' + $OcclusionQuery + '"')
        Write-Config $text
    }
}

$result = Get-SettingsResult $text $backup $Action
if ($Json) { $result | ConvertTo-Json -Depth 5 -Compress } else { [pscustomobject]$result }
