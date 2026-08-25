[CmdletBinding()]
param([string]$Configuration = 'Release')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$artifacts = Join-Path $root '.artifacts/launcher'
$publish = Join-Path $artifacts 'publish'
$payloadRoot = Join-Path $artifacts 'payload'
$payloadZip = Join-Path $publish 'pinyon-shift-source.zip'
$releaseZip = Join-Path $root '.artifacts/PinyonShift-Launcher.zip'
foreach ($path in @($publish, $payloadRoot)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    [void](New-Item -ItemType Directory -Force -Path $path)
}

& dotnet publish (Join-Path $root 'launcher/PinyonShift.Launcher/PinyonShift.Launcher.csproj') `
    -c $Configuration -r win-x64 --self-contained true -o $publish
if ($LASTEXITCODE -ne 0) { throw 'Launcher publish failed.' }

$include = @(
    'CMakeLists.txt', 'CMakePresets.json', 'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md',
    'cmake', 'config/release.json', 'config/release-toolchain.json', 'config/supported-dumps.json',
    'config/rexglue', 'patches/rexglue', 'src',
    'tools/build-preview.ps1', 'tools/create-crash-report.ps1', 'tools/install-build-tools.ps1',
    'tools/launch-preview.ps1', 'tools/prepare-rexglue.ps1',
    'tools/provision-toolchain.ps1', 'tools/release-common.ps1',
    'tools/setup-preview.ps1', 'tools/verify-game.ps1'
)
foreach ($relative in $include) {
    $source = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $destination = Join-Path $payloadRoot $relative
    if (Test-Path -LiteralPath $source -PathType Container) {
        [void](New-Item -ItemType Directory -Force -Path $destination)
        Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $destination -Recurse -Force
    }
    else {
        [void](New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent))
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

Get-ChildItem -LiteralPath $payloadRoot -Recurse -File | Where-Object {
    $_.Extension -in @('.exe', '.dll', '.obj', '.lib', '.pdb', '.iso', '.xex')
} | ForEach-Object { throw "Forbidden file entered launcher payload: $($_.FullName)" }

Compress-Archive -Path (Join-Path $payloadRoot '*') -DestinationPath $payloadZip -CompressionLevel Optimal
if (Test-Path -LiteralPath $releaseZip) { Remove-Item -LiteralPath $releaseZip -Force }
Compress-Archive -Path (Join-Path $publish '*') -DestinationPath $releaseZip -CompressionLevel Optimal

[pscustomobject]@{
    launcher = Join-Path $publish 'PinyonShiftLauncher.exe'
    source_payload = $payloadZip
    release = $releaseZip
    release_sha256 = (Get-FileHash -LiteralPath $releaseZip -Algorithm SHA256).Hash
}
