[CmdletBinding()]
param(
    # Where the kit's build tree goes; a fresh folder outside the checkout
    # keeps it apart from the developer build.
    [Parameter(Mandatory)] [string]$BuildRoot,
    # The kit archive to write (a .zip).
    [Parameter(Mandatory)] [string]$Output,
    [ValidateRange(0, 64)] [int]$Parallel = 0
)

# TP-2 and TP-3 (docs/TIME_TO_PLAY_BACKLOG.md): build the ShiftGlue kit that
# setup downloads instead of cloning and compiling ShiftGlue: the code
# generator, the runtime and graphics backend DLLs with their import
# libraries, and the headers and CMake package the game build consumes.
# Nothing in it is game-derived.

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
if ($Parallel -eq 0) { $Parallel = Get-PinyonBuildJobCount }
$env:SOURCE_DATE_EPOCH = '1784764800'

$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
$buildTree = Join-Path $BuildRoot 'build'
$prefix = Join-Path $BuildRoot 'kit'
$logs = Join-Path $BuildRoot 'logs'
foreach ($folder in @($buildTree, $logs)) { [void](New-Item -ItemType Directory -Force -Path $folder) }
if (Test-Path -LiteralPath $prefix) { Remove-Item -LiteralPath $prefix -Recurse -Force }

$revision = (& (Get-PinyonGit) -C $sdkRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($revision -ne $config.rexglue.revision) {
    throw "ShiftGlue is at $revision, but config/release-toolchain.json pins $($config.rexglue.revision)."
}

# The options every Pinyon Shift build compiles the SDK with
# (cmake/PinyonShiftRexGlue.cmake), fixed for the kit: Release, the SSE4.1
# baseline, perf counters on, Tracy off. The source prefix map keeps the
# build machine's paths out of the binaries.
$flags = "-msse4.1 -DREXGLUE_ENABLE_PERF_COUNTERS -ffile-prefix-map=$($sdkRoot -replace '\\', '/')=shiftglue"
Invoke-PinyonBuildCommand $environment.CMake @('-S', $sdkRoot, '-B', $buildTree, '-G', 'Ninja',
    '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++',
    "-DCMAKE_C_FLAGS=$flags", "-DCMAKE_CXX_FLAGS=$flags",
    '-DREXGLUE_USE_VULKAN=ON', '-DREXGLUE_ENABLE_TRACY=OFF', '-DSDL_HIDAPI_LIBUSB=OFF',
    '-DREXGLUE_INSTALL_REGISTER_PACKAGE=OFF', "-DPYTHON_EXECUTABLE=$(Get-PinyonPython)",
    "-DCMAKE_INSTALL_PREFIX=$prefix", '-DCMAKE_LINKER_TYPE=LLD', '-DCMAKE_EXE_LINKER_FLAGS=-Xlinker /Brepro',
    '-DCMAKE_SHARED_LINKER_FLAGS=-Xlinker /Brepro') `
    (Join-Path $logs 'configure.log') 'ShiftGlue kit configuration failed.' -Step 'Configure the ShiftGlue kit'
Invoke-PinyonBuildCommand $environment.CMake @('--build', $buildTree, '--target', 'install',
    '--parallel', "$Parallel") (Join-Path $logs 'build.log') 'ShiftGlue kit build failed.' -Step 'Build the ShiftGlue kit'

$rexglueExe = Join-Path $prefix 'bin/rexglue.exe'
Invoke-PinyonBuildCommand 'mt.exe' @('-nologo', "-inputresource:$rexglueExe;#1",
    '-manifest', (Join-Path $root 'config/rexglue/codegen-windows.manifest'),
    "-outputresource:$rexglueExe;#1") (Join-Path $logs 'manifest.log') `
    'Could not enable Unicode paths for the code generator.' -Step 'Configure code generator Unicode paths'

# SDK files the host compiles or includes itself, at their source-tree paths
# (PINYON_SHIFT_SDK_SOURCE_DIR in cmake/PinyonShiftRexGlue.cmake).
$mirror = Join-Path $prefix 'share/rexglue/source'
foreach ($item in @(
    @{ From = 'thirdparty/crypto'; Filter = 'sha256.*' },
    @{ From = 'thirdparty/imgui'; Filter = '*.h' },
    @{ From = 'thirdparty/renderdoc'; Filter = '*.h' },
    @{ From = 'thirdparty/tomlplusplus/include'; Filter = '*'; Recurse = $true },
    @{ From = '.'; Filter = 'LICENSE*' }
)) {
    $from = Join-Path $sdkRoot $item.From
    $to = Join-Path $mirror $item.From
    [void](New-Item -ItemType Directory -Force -Path $to)
    if ($item.ContainsKey('Recurse')) { Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force }
    else { Copy-Item -Path (Join-Path $from $item.Filter) -Destination $to }
}

# No vendor binary goes in the kit (docs/LEGAL.md): AMD's signed FidelityFX
# DLL and NVIDIA's DLSS runtime are fetched at the game's configure, pinned
# and hashed, by the same SDK modules a source build runs.
$modules = Join-Path $prefix 'share/rexglue/cmake'
[void](New-Item -ItemType Directory -Force -Path $modules)
foreach ($module in @('rexglue_dlss.cmake', 'rexglue_ffx_api_headers.cmake')) {
    Copy-Item -LiteralPath (Join-Path $sdkRoot "cmake/$module") -Destination $modules
}
$ffxNotice = Join-Path $prefix 'share/rexglue/upscalers/fidelityfx'
[void](New-Item -ItemType Directory -Force -Path $ffxNotice)
Copy-Item -LiteralPath (Join-Path $sdkRoot 'thirdparty/fidelityfx-vk/LICENSE.txt') -Destination $ffxNotice

# The Microsoft C++ runtime the kit's DLLs were built against, staged beside
# the game when it is newer than the one the player's tools provide.
$redist = Get-ChildItem -LiteralPath (Join-Path $environment.VisualStudioRoot 'VC/Redist/MSVC') -Directory |
    Where-Object { $_.Name -match '^\d+\.' } | Sort-Object { [version]$_.Name } | Select-Object -Last 1
$crt = Get-ChildItem -LiteralPath (Join-Path $redist.FullName 'x64') -Directory -Filter 'Microsoft.VC*.CRT' |
    Select-Object -First 1
$crtTarget = Join-Path $prefix 'redist'
[void](New-Item -ItemType Directory -Force -Path $crtTarget)
Copy-Item -Path (Join-Path $crt.FullName '*.dll') -Destination $crtTarget

$kit = [ordered]@{
    schema_version = 1
    platform = 'windows-x64'
    shiftglue_revision = $revision
    llvm = $config.llvm.version
    msvc_toolset = $env:VCToolsVersion
    windows_sdk = $env:WindowsSDKVersion.TrimEnd('\')
    cpu_baseline = 'sse4.1'
    configuration = 'Release'
}
[IO.File]::WriteAllText((Join-Path $prefix 'kit.json'), (($kit | ConvertTo-Json) + [Environment]::NewLine),
    [Text.UTF8Encoding]::new($false))

& (Get-PinyonPython) -I (Join-Path $PSScriptRoot 'repack-toolchain.py') kit --source $prefix --output $Output `
    --top "shiftglue-kit"
if ($LASTEXITCODE -ne 0) { throw 'Could not write the kit archive.' }
