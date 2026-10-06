[CmdletBinding()]
param(
    [ValidateSet('Release', 'RelWithDebInfo')]
    [string]$Configuration = 'Release',
    # 0 picks a job count from the logical processors and installed memory.
    [ValidateRange(0, 32)] [int]$Parallel = 0,
    [switch]$CleanGenerated,
    # NP-3.5: 'auto' builds with FMA3 when this CPU has it (a faster build of
    # the same results); the build only runs on CPUs with the chosen baseline.
    [ValidateSet('auto', 'sse4.1', 'fma')]
    [string]$CpuBaseline = 'auto',
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
$sdkRoot = Resolve-PinyonRexGlueRoot
$generatedRoot = Resolve-PinyonLocalPath -RelativePath '.local/generated'
$rexglueExe = Join-Path $sdkRoot 'out/win-amd64/Release/rexglue.exe'
$manifest = Join-Path $root 'config/rexglue/pinyon_shift_manifest.toml'
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)
$env:SOURCE_DATE_EPOCH = '1784764800'
$previewPreset = 'win-amd64-' + $Configuration.ToLowerInvariant()
if ($Parallel -eq 0) { $Parallel = Get-PinyonBuildJobCount }
function Test-PinyonCpuFma {
    # Windows reports AVX2 only when it also saves the AVX register state, and
    # every CPU with AVX2 has FMA3.
    if (-not ('PinyonShift.CpuFeatures' -as [type])) {
        Add-Type -Namespace PinyonShift -Name CpuFeatures -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern bool IsProcessorFeaturePresent(uint feature);
'@
    }
    return [PinyonShift.CpuFeatures]::IsProcessorFeaturePresent(40)
}
$cpuBaseline = if ($CpuBaseline -ne 'auto') { $CpuBaseline }
    elseif (Test-PinyonCpuFma) { 'fma' } else { 'sse4.1' }
$cpuFlags = if ($cpuBaseline -eq 'fma') { '-msse4.1 -mfma -ffp-contract=off' } else { '-msse4.1' }

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
$memoryBytes = Get-PinyonTotalMemoryBytes
$memoryText = if ($memoryBytes -gt 0) { ", $([Math]::Round($memoryBytes / 1GB)) GB memory" } else { '' }
Write-PinyonEvent build 62 "Compiling with $Parallel parallel jobs ($([Environment]::ProcessorCount) logical processors$memoryText)." -JsonEvents:$JsonEvents
# A folder moved since the last build (a portable install) is configured afresh.
foreach ($buildTree in @((Join-Path $sdkRoot 'out/build/win-amd64'), (Join-Path $root "out/build/$previewPreset"))) {
    if (Reset-PinyonRelocatedCMakeCache -BuildDirectory $buildTree) {
        Write-PinyonEvent build 62 "The build folder moved; configuring $buildTree again." -JsonEvents:$JsonEvents
    }
}
Push-Location $sdkRoot
try {
    Invoke-PinyonBuildCommand $environment.CMake @('--preset', 'win-amd64',
        '-DREXGLUE_ENABLE_TRACY=OFF', '-DSDL_HIDAPI_LIBUSB=OFF') `
        (Join-Path $logs 'rexglue-configure.log') 'ReXGlue configuration failed.' -Step 'Configure the ReXGlue code generator'
    Invoke-PinyonBuildCommand $environment.CMake @('--build', '--preset', 'win-amd64-release',
        '--target', 'rexglue', '--parallel', "$Parallel") `
        (Join-Path $logs 'rexglue-build.log') 'ReXGlue code-generator build failed.' -Step 'Build the ReXGlue code generator'
}
finally { Pop-Location }
if (-not (Test-Path -LiteralPath $rexglueExe -PathType Leaf)) {
    throw "The ReXGlue code generator was not produced: $rexglueExe"
}

Write-PinyonEvent build 72 'Translating the verified game code locally.' -JsonEvents:$JsonEvents
$generatedTrees = @('default', 'speech', 'xmedia')
$codegenLog = Join-Path $logs 'codegen.log'
$codegenConsoleLog = Join-Path $logs 'codegen-console.log'
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
    Invoke-PinyonLoggedCommand -FilePath $rexglueExe -Arguments @(
        '--log-level', 'info', '--log-file', $codegenLog, 'codegen', $manifest) `
        -LogPath $codegenConsoleLog | Out-Host
    $codegenExit = $LASTEXITCODE
    if ($codegenExit -ne 0) {
        foreach ($tree in $generatedTrees) {
            $stamp = Join-Path $generatedRoot "$tree/codegen.build.stamp"
            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
        }
        throw (New-PinyonCommandFailure -FailureMessage 'Local code generation failed; incomplete generation stamps were removed.' `
            -Step 'Translate the game code' -LogPath $codegenConsoleLog -ExitCode $codegenExit `
            -CommandLine (Format-PinyonCommandLine -FilePath $rexglueExe -Arguments @(
                '--log-level', 'info', '--log-file', $codegenLog, 'codegen', $manifest)))
    }
    try {
        & (Join-Path $PSScriptRoot 'verify-codegen-log.ps1') -LogPath $codegenLog | Out-Host
    }
    catch {
        foreach ($tree in $generatedTrees) {
            $stamp = Join-Path $generatedRoot "$tree/codegen.build.stamp"
            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
        }
        throw "Code generation emitted an unreviewed warning; generation stamps were removed. $($_.Exception.Message)"
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
    Write-PinyonEvent build 83 "CPU baseline: $cpuBaseline." -JsonEvents:$JsonEvents
    # The presets build the Vulkan backend, whose glslang reads its version
    # through Python: the pinned runtime, since a pyenv shim breaks that.
    Invoke-PinyonBuildCommand $environment.CMake @('--preset', $previewPreset, "-DREXSDK_DIR=$sdkRoot",
        "-DPINYON_SHIFT_CPU_BASELINE=$cpuBaseline", "-DCMAKE_C_FLAGS=$cpuFlags",
        "-DCMAKE_CXX_FLAGS=$cpuFlags", "-DPYTHON_EXECUTABLE=$(Get-PinyonPython)") `
        (Join-Path $logs 'preview-configure.log') 'Preview configuration failed.' -Step 'Configure the game build'
    Invoke-PinyonBuildCommand $environment.CMake @('--build', '--preset', $previewPreset, '--parallel', "$Parallel") `
        (Join-Path $logs 'preview-build.log') 'Preview compilation failed.' -Step 'Compile the game'
}
finally { Pop-Location }

$executable = Join-Path $root "out/build/$previewPreset/pinyon_shift.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'Compilation completed without producing pinyon_shift.exe.'
}
$manifestName = if ($Configuration -eq 'Release') { 'build.json' } else { 'build-profile.json' }
$manifestPath = Resolve-PinyonLocalPath -RelativePath ".local/$manifestName"
$git = Get-PinyonGit
$sourceProvenance = Get-PinyonSourceProvenance -Root $root -Git $git
$sourceCommit = $sourceProvenance.Commit
$sourceDirty = $sourceProvenance.Dirty

$rexglueCommit = @(& $git -C $sdkRoot rev-parse HEAD 2>$null | Select-Object -First 1)
if ($rexglueCommit.Count -ne 1 -or
    $rexglueCommit[0] -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Build provenance requires an exact ShiftGlue commit.'
}
$rexglueCommit = $rexglueCommit[0].ToLowerInvariant()
$rexglueDirty = @(& $git -C $sdkRoot status --porcelain --ignore-submodules=dirty).Count -ne 0
$payloadMarkerPath = Join-Path $root '.pinyon-source-sha256'
$payloadSha256 = if (Test-Path -LiteralPath $payloadMarkerPath -PathType Leaf) {
    (Get-Content -LiteralPath $payloadMarkerPath -Raw).Trim().ToUpperInvariant()
} else { '' }
$executableSha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
$result = [ordered]@{
    schema_version = 3
    configuration = $Configuration
    cpu_baseline = $cpuBaseline
    created_utc = [DateTime]::UtcNow.ToString('o')
    executable = "out/build/$previewPreset/pinyon_shift.exe"
    executable_sha256 = $executableSha256
    generated_locally = $true
    pinyon_shift_commit = $sourceCommit
    pinyon_shift_dirty = $sourceDirty.ToString().ToLowerInvariant()
    pinyon_shift_source_payload_sha256 = $payloadSha256
    rexglue_commit = $rexglueCommit
    rexglue_dirty = $rexglueDirty.ToString().ToLowerInvariant()
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
