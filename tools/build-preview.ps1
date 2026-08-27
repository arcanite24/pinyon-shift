[CmdletBinding()]
param(
    [ValidateRange(1, 32)] [int]$Parallel = [Math]::Max(2, [Math]::Min(16, [Environment]::ProcessorCount - 1)),
    [switch]$CleanGenerated,
    [switch]$JsonEvents
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$environment = Enter-PinyonBuildEnvironment
$sdkRoot = Resolve-PinyonLocalPath -RelativePath $config.rexglue.path
$generatedRoot = Resolve-PinyonLocalPath -RelativePath '.local/generated'
$rexglueExe = Join-Path $sdkRoot 'out/win-amd64/Release/rexglue.exe'
$manifest = Join-Path $root 'config/rexglue/pinyon_shift_manifest.toml'
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)
$env:SOURCE_DATE_EPOCH = '1784764800'

$supportedDumps = Get-Content -LiteralPath (Join-Path $root 'config/supported-dumps.json') -Raw |
    ConvertFrom-Json
$supportedXex = $supportedDumps.dumps[0].executables |
    Where-Object { $_.guest_path -eq 'default.xex' } | Select-Object -First 1
$gameXex = Resolve-PinyonLocalPath -RelativePath '.local/game/base/default.xex'
if ($null -eq $supportedXex -or -not (Test-Path -LiteralPath $gameXex -PathType Leaf)) {
    throw 'The supported default.xex is not available for code generation.'
}
$gameXexInfo = Get-Item -LiteralPath $gameXex
$gameXexSha256 = (Get-FileHash -LiteralPath $gameXex -Algorithm SHA256).Hash
if ($gameXexInfo.Length -ne [int64]$supportedXex.size_bytes -or
    $gameXexSha256 -ne $supportedXex.sha256) {
    throw 'default.xex does not match the exact supported EPIC-08 patch target.'
}
$guestPatchPath = Join-Path $root 'config/rexglue/analysis/fh1-post-processing.toml'
$guestPatchSetSha256 = (Get-FileHash -LiteralPath $guestPatchPath -Algorithm SHA256).Hash

Write-PinyonEvent build 62 'Building the local code generator.' -JsonEvents:$JsonEvents
Push-Location $sdkRoot
try {
    & $environment.CMake --preset win-amd64 `
        -DREXGLUE_ENABLE_TRACY=OFF -DSDL_HIDAPI_LIBUSB=OFF
    if ($LASTEXITCODE -ne 0) { throw 'ReXGlue configuration failed.' }
    & $environment.CMake --build --preset win-amd64-release --target rexglue --parallel $Parallel
    if ($LASTEXITCODE -ne 0) { throw 'ReXGlue code-generator build failed.' }
}
finally { Pop-Location }
if (-not (Test-Path -LiteralPath $rexglueExe -PathType Leaf)) {
    throw "The ReXGlue code generator was not produced: $rexglueExe"
}

Write-PinyonEvent build 72 'Translating the verified game code locally.' -JsonEvents:$JsonEvents
$generatedTrees = @('default', 'speech', 'xmedia')
$codegenLog = Join-Path $logs 'codegen.log'
if ($CleanGenerated -and (Test-Path -LiteralPath $generatedRoot)) {
    Remove-Item -LiteralPath $generatedRoot -Recurse -Force
}
$requiresBootstrap = $CleanGenerated -or
    -not (Test-Path -LiteralPath (Join-Path $generatedRoot 'default/codegen.build.stamp') -PathType Leaf)
foreach ($tree in $generatedTrees) {
    if (-not (Test-Path -LiteralPath (Join-Path $generatedRoot "$tree/sources.cmake") -PathType Leaf)) {
        $requiresBootstrap = $true
    }
}
if ($requiresBootstrap) {
    [void](New-Item -ItemType Directory -Force -Path $generatedRoot)
    if (Test-Path -LiteralPath $codegenLog) {
        Remove-Item -LiteralPath $codegenLog -Force
    }
    & $rexglueExe --log-level info --log-file $codegenLog codegen $manifest
    if ($LASTEXITCODE -ne 0) {
        foreach ($tree in $generatedTrees) {
            $stamp = Join-Path $generatedRoot "$tree/codegen.build.stamp"
            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
        }
        throw 'Local code generation failed; incomplete generation stamps were removed.'
    }
    & python (Join-Path $PSScriptRoot 'verify-codegen-log.py') $codegenLog
    if ($LASTEXITCODE -ne 0) {
        foreach ($tree in $generatedTrees) {
            $stamp = Join-Path $generatedRoot "$tree/codegen.build.stamp"
            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
        }
        throw 'Code generation emitted an unreviewed warning; generation stamps were removed.'
    }
}
else {
    Write-PinyonEvent build 74 'Generated trees are present; checking dependency stamps during the build.' -JsonEvents:$JsonEvents
}
foreach ($tree in $generatedTrees) {
    if (-not (Test-Path -LiteralPath (Join-Path $generatedRoot "$tree/sources.cmake") -PathType Leaf)) {
        throw "Generated source tree is incomplete: $tree"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $generatedRoot 'default/codegen.build.stamp') -PathType Leaf)) {
    throw 'Generated source tree is incomplete: default/codegen.build.stamp'
}

Write-PinyonEvent build 82 'Compiling the playable preview. This is the longest step.' -JsonEvents:$JsonEvents
Push-Location $root
try {
    & $environment.CMake --preset win-amd64-release
    if ($LASTEXITCODE -ne 0) { throw 'Preview configuration failed.' }
    & $environment.CMake --build --preset win-amd64-release --parallel $Parallel
    if ($LASTEXITCODE -ne 0) { throw 'Preview compilation failed.' }
}
finally { Pop-Location }

$executable = Join-Path $root 'out/build/win-amd64-release/pinyon_shift.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'Compilation completed without producing pinyon_shift.exe.'
}
$manifestPath = Resolve-PinyonLocalPath -RelativePath '.local/build.json'
$git = Get-PinyonGit
$sourceProvenancePath = Join-Path $root 'config/source-provenance.json'
$sourceCommit = $null
$sourceDirty = $false
$gitCommit = @(& $git -C $root rev-parse HEAD 2>$null | Select-Object -First 1)
if ($gitCommit.Count -eq 1 -and $gitCommit[0] -match '^[0-9a-fA-F]{40}$') {
    $sourceCommit = $gitCommit[0].ToLowerInvariant()
    $sourceDirty = @(& $git -C $root status --porcelain).Count -ne 0
}
elseif (Test-Path -LiteralPath $sourceProvenancePath -PathType Leaf) {
    $sourceProvenance = Get-Content -LiteralPath $sourceProvenancePath -Raw | ConvertFrom-Json
    if ($sourceProvenance.commit -match '^[0-9a-fA-F]{40}$') {
        $sourceCommit = $sourceProvenance.commit.ToLowerInvariant()
        $sourceDirty = [bool]$sourceProvenance.dirty
    }
}
if (-not $sourceCommit) {
    throw 'Build provenance requires an exact Pinyon Shift commit.'
}

$patchMarkerPath = Join-Path $sdkRoot '.pinyon-patches.json'
if (-not (Test-Path -LiteralPath $patchMarkerPath -PathType Leaf)) {
    throw 'Build provenance requires the applied ReXGlue patch marker.'
}
$patchMarker = Get-Content -LiteralPath $patchMarkerPath -Raw | ConvertFrom-Json
$rexglueCommit = @(& $git -C $sdkRoot rev-parse HEAD 2>$null | Select-Object -First 1)
if ($rexglueCommit.Count -ne 1 -or
    $rexglueCommit[0] -notmatch '^[0-9a-fA-F]{40}$' -or
    $rexglueCommit[0] -ne $config.rexglue.base_commit -or
    $patchMarker.base_commit -ne $config.rexglue.base_commit) {
    throw 'The prepared ReXGlue revision does not match the pinned build configuration.'
}
$rexglueCommit = $rexglueCommit[0].ToLowerInvariant()
$payloadMarkerPath = Join-Path $root '.pinyon-source-sha256'
$payloadSha256 = if (Test-Path -LiteralPath $payloadMarkerPath -PathType Leaf) {
    (Get-Content -LiteralPath $payloadMarkerPath -Raw).Trim().ToUpperInvariant()
} else { '' }
$executableSha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
$patchSetSha256 = (Get-FileHash -LiteralPath $patchMarkerPath -Algorithm SHA256).Hash
$result = [ordered]@{
    schema_version = 2
    created_utc = [DateTime]::UtcNow.ToString('o')
    executable = 'out/build/win-amd64-release/pinyon_shift.exe'
    executable_sha256 = $executableSha256
    generated_locally = $true
    pinyon_shift_commit = $sourceCommit
    pinyon_shift_dirty = $sourceDirty.ToString().ToLowerInvariant()
    pinyon_shift_source_payload_sha256 = $payloadSha256
    rexglue_commit = $rexglueCommit
    rexglue_patch_set_sha256 = $patchSetSha256
    rexglue_patch_count = @($patchMarker.patches).Count.ToString()
    guest_executable_sha256 = $gameXexSha256
    guest_codegen_patch_profile = 'fh1-retail-base-post-processing-v1'
    guest_codegen_patch_set_sha256 = $guestPatchSetSha256
}
$resultJson = ($result | ConvertTo-Json) + [Environment]::NewLine
[IO.File]::WriteAllText($manifestPath, $resultJson,
    [Text.UTF8Encoding]::new($false))
$runtimeManifestPath = Join-Path (Split-Path $executable -Parent) 'pinyon_shift_build.json'
[IO.File]::WriteAllText($runtimeManifestPath, $resultJson,
    [Text.UTF8Encoding]::new($false))
Write-PinyonEvent build 96 'Local compilation completed successfully.' -JsonEvents:$JsonEvents
$result
