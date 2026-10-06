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

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
function New-DeterministicZip {
    param(
        [Parameter(Mandatory)] [string]$SourceDirectory,
        [Parameter(Mandatory)] [string]$DestinationPath
    )

    if (Test-Path -LiteralPath $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Force
    }
    $fixedTimestamp = [DateTimeOffset]::FromUnixTimeSeconds(1784764800)
    $archive = [IO.Compression.ZipFile]::Open(
        $DestinationPath, [IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -LiteralPath $SourceDirectory -Recurse -File |
            Sort-Object { $_.FullName.Substring($SourceDirectory.Length).Replace([char]92, [char]47) } |
            ForEach-Object {
                $entryName = $_.FullName.Substring($SourceDirectory.Length).TrimStart([char]92, [char]47).Replace([char]92, [char]47)
                $entry = $archive.CreateEntry(
                    $entryName, [IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = $fixedTimestamp
                $sourceStream = [IO.File]::OpenRead($_.FullName)
                $entryStream = $entry.Open()
                try {
                    $sourceStream.CopyTo($entryStream)
                }
                finally {
                    $entryStream.Dispose()
                    $sourceStream.Dispose()
                }
            }
    }
    finally {
        $archive.Dispose()
    }
}

foreach ($path in @($publish, $payloadRoot)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    [void](New-Item -ItemType Directory -Force -Path $path)
}

$release = Get-Content (Join-Path $root 'config/release.json') -Raw | ConvertFrom-Json
# Keep AssemblyVersion (the existing installation directory) stable so updates
# retain user state, while Windows file/product metadata identifies this release.
$fileVersion = ($release.version -split '-', 2)[0] + '.0'
& dotnet publish (Join-Path $root 'launcher/PinyonShift.Launcher/PinyonShift.Launcher.csproj') `
    -c $Configuration -r win-x64 --self-contained true -o $publish `
    "-p:BaseOutputPath=$(Join-Path $artifacts 'build')/" `
    "-p:Version=$($release.version)" "-p:FileVersion=$fileVersion"
if ($LASTEXITCODE -ne 0) { throw 'Launcher publish failed.' }

$include = @(
    'CMakeLists.txt', 'CMakePresets.json', 'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md',
    'cmake', 'config/gamecontrollerdb.txt', 'config/release.json', 'config/release-toolchain.json', 'config/supported-dumps.json',
    'config/supported-extracted-ms-2505.json', 'tools/verify-extracted-game.ps1', 'docs/EXTRACTED_GAME_INPUT.md',
    'config/rexglue', 'include', 'mods_src', 'src', 'tests/config', 'tests/native_renderer',
    'tests/save', 'tests/ui',
    'tools/fh1_archive_extract.cpp', 'tools/fh1_texture_import.cpp', 'tools/thread_sampler.cpp',
    'tools/extract-fh1-shader-corpus.py', 'tools/build-fh1-gpu-prewarm.py',
    'tools/produce-fh1-artifacts.ps1', 'tools/prepare-fh1-shaders.ps1', 'tools/prepare-fh1-vulkan.ps1',
    'config/render-tests',
    'tools/build-preview.ps1', 'tools/create-crash-report.ps1', 'tools/install-build-tools.ps1',
    'tools/launch-preview.ps1', 'tools/prepare-rexglue.ps1',
    'tools/build-mod-patches.py', 'tools/build-mod-archives.py', 'tools/install-sample-mod.py',
    'tools/pinyon.py', 'tools/pinyon_android.py', 'tools/build-android.ps1',
    'config/android-toolchain.json', 'android',
    'tools/fh1-profile.py', 'tools/fh1-strings.py', 'tools/inspect-fh1-ui.py',
    'tools/native-shader-pack.py',
    'tools/provision-toolchain.ps1', 'tools/release-common.ps1',
    'tools/host-config.ps1', 'tools/set-graphics-experiment.ps1', 'tools/setup-preview.ps1',
    'tools/verify-codegen-log.ps1', 'tools/verify-game.ps1'
)
foreach ($relative in $include) {
    $source = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $source)) { throw "Required launcher payload source is missing: $relative" }
    $destination = Join-Path $payloadRoot $relative
    if (Test-Path -LiteralPath $source -PathType Container) {
        [void](New-Item -ItemType Directory -Force -Path $destination)
        $children = Get-ChildItem -LiteralPath $source -Force
        if ($relative -eq 'config/rexglue') {
            $children = $children | Where-Object { $_.Name -ne 'generated' }
        }
        $children | Copy-Item -Destination $destination -Recurse -Force
    }
    else {
        [void](New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent))
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

$git = Get-Command git.exe -ErrorAction Stop
$sourceCommit = @(& $git.Source -C $root rev-parse HEAD 2>$null | Select-Object -First 1)
if ($sourceCommit.Count -ne 1 -or $sourceCommit[0] -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Unable to record the Pinyon Shift source commit for the launcher payload.'
}
$sourceCommit = $sourceCommit[0].ToLowerInvariant()
$sourceDirty = @(& $git.Source -C $root status --porcelain).Count -ne 0
$sourceProvenance = [ordered]@{
    schema_version = 1
    repository = 'https://github.com/arcanite24/pinyon-shift'
    commit = $sourceCommit
    dirty = $sourceDirty
}
$sourceProvenancePath = Join-Path $payloadRoot 'config/source-provenance.json'
[IO.File]::WriteAllText($sourceProvenancePath,
    ($sourceProvenance | ConvertTo-Json) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))

Get-ChildItem -LiteralPath $payloadRoot -Recurse -File | Where-Object {
    $_.Extension -in @('.exe', '.dll', '.obj', '.lib', '.pdb', '.iso', '.xex', '.dxil', '.pnsp',
        '.so', '.apk', '.aab', '.idsig', '.keystore', '.jks', '.dex')
} | ForEach-Object { throw "Forbidden file entered launcher payload: $($_.FullName)" }

New-DeterministicZip -SourceDirectory $payloadRoot -DestinationPath $payloadZip
New-DeterministicZip -SourceDirectory $publish -DestinationPath $releaseZip

[pscustomobject]@{
    launcher = Join-Path $publish 'PinyonShiftLauncher.exe'
    source_payload = $payloadZip
    release = $releaseZip
    release_sha256 = (Get-FileHash -LiteralPath $releaseZip -Algorithm SHA256).Hash
}
