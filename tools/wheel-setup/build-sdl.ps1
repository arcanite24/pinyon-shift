# Builds SDL3.dll for the launcher's wheel screen from the game SDK's own SDL3 source, so joystick
# names, paths and numbering match what the game sees. tools/package-launcher.ps1 runs it when
# launcher/PinyonShift.Launcher/Wheel/Native/SDL3.dll is missing.
#   powershell -File tools\wheel-setup\build-sdl.ps1 [-Sdk <shiftglue-sdk checkout>]
# Needs the VS 2022 C++ build tools and CMake; Ninja when it is on PATH, else Visual Studio's own
# generator. A checkout made without recursive submodules (as the release workflow's) gets the SDK's
# SDL3 submodule here.
param([string]$Sdk = (Join-Path $PSScriptRoot '..\..\thirdparty\shiftglue-sdk'))
$ErrorActionPreference = 'Stop'
$native = Join-Path $PSScriptRoot 'native'
$build = Join-Path $native 'build'
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vcvars = if (Test-Path $vswhere) {
    & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find 'VC\Auxiliary\Build\vcvars64.bat'
}
if (-not $vcvars) { throw 'The VS 2022 C++ build tools are needed to build SDL3.dll.' }
$sdkPath = (Resolve-Path $Sdk).Path
if (-not (Test-Path (Join-Path $sdkPath 'thirdparty\sdl3\CMakeLists.txt'))) {
    Write-Host 'Fetching the SDK''s SDL3 source (thirdparty/sdl3)...'
    & git -C $sdkPath submodule update --init --depth 1 thirdparty/sdl3
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $sdkPath 'thirdparty\sdl3\CMakeLists.txt'))) {
        throw "No SDL3 source in $sdkPath\thirdparty\sdl3 and it could not be fetched."
    }
}
$generator = if (Get-Command ninja -ErrorAction SilentlyContinue) {
    '-G Ninja -DCMAKE_BUILD_TYPE=Release'
} else {
    '-G "Visual Studio 17 2022" -A x64'
}
cmd /c "`"$vcvars`" >nul && cmake -S `"$native`" -B `"$build`" $generator -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DSHIFTGLUE_SDK=`"$sdkPath`" && cmake --build `"$build`" --config Release"
if ($LASTEXITCODE -ne 0) { throw 'SDL3.dll build failed' }
# Ninja writes build\sdl3\SDL3.dll; the Visual Studio generator a Release folder below it.
$dll = Get-ChildItem (Join-Path $build 'sdl3') -Recurse -Filter SDL3.dll | Sort-Object LastWriteTime | Select-Object -Last 1
if (-not $dll) { throw "SDL3.dll was not produced under $build\sdl3" }
$target = Join-Path $PSScriptRoot '..\..\launcher\PinyonShift.Launcher\Wheel\Native'
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item $dll.FullName (Join-Path $target 'SDL3.dll') -Force
Write-Host "Built $(Join-Path (Resolve-Path $target) 'SDL3.dll')"
