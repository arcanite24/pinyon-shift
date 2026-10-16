# Builds SDL3.dll for the launcher's wheel screen from the game SDK's own SDL3 source, so joystick
# names, paths and numbering match what the game sees. tools/package-launcher.ps1 runs it when
# launcher/PinyonShift.Launcher/Wheel/Native/SDL3.dll is missing.
#   powershell -File tools\wheel-setup\build-sdl.ps1 [-Sdk <shiftglue-sdk checkout>]
# Needs the VS 2022 C++ build tools, CMake and Ninja.
param([string]$Sdk = (Join-Path $PSScriptRoot '..\..\thirdparty\shiftglue-sdk'))
$ErrorActionPreference = 'Stop'
$native = Join-Path $PSScriptRoot 'native'
$build = Join-Path $native 'build'
$vcvars = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * `
    -find 'VC\Auxiliary\Build\vcvars64.bat'
if (-not $vcvars) { throw 'The VS 2022 C++ build tools are needed to build SDL3.dll.' }
$sdkPath = (Resolve-Path $Sdk).Path
if (-not (Test-Path (Join-Path $sdkPath 'thirdparty\sdl3\CMakeLists.txt'))) {
    throw "No SDL3 source in $sdkPath\thirdparty\sdl3 (check out the SDK's submodules)."
}
cmd /c "`"$vcvars`" >nul && cmake -S `"$native`" -B `"$build`" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DSHIFTGLUE_SDK=`"$sdkPath`" && cmake --build `"$build`""
if ($LASTEXITCODE -ne 0) { throw 'SDL3.dll build failed' }
$target = Join-Path $PSScriptRoot '..\..\launcher\PinyonShift.Launcher\Wheel\Native'
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item (Join-Path $build 'sdl3\SDL3.dll') (Join-Path $target 'SDL3.dll') -Force
Write-Host "Built $(Join-Path (Resolve-Path $target) 'SDL3.dll')"
