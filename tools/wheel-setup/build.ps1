# Builds PinyonWheelSetup.exe: one self-contained EXE (the .NET runtime and SDL3.dll inside).
#   powershell -File tools\wheel-setup\build.ps1 [-Sdk <shiftglue-sdk checkout>] [-Out <folder>]
# Needs the VS 2022 C++ build tools (for SDL3.dll), CMake, Ninja and the .NET 8 SDK. SDL3.dll is
# built from the SDK's own SDL3 source so joystick numbering matches the game.
param(
    [string]$Sdk = (Join-Path $PSScriptRoot '..\..\thirdparty\shiftglue-sdk'),
    [string]$Out = (Join-Path $PSScriptRoot 'publish')
)
$ErrorActionPreference = 'Stop'
$native = Join-Path $PSScriptRoot 'native'
$build = Join-Path $native 'build'
$vcvars = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * `
    -find 'VC\Auxiliary\Build\vcvars64.bat'
$sdkPath = (Resolve-Path $Sdk).Path
cmd /c "`"$vcvars`" >nul && cmake -S `"$native`" -B `"$build`" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DSHIFTGLUE_SDK=`"$sdkPath`" && cmake --build `"$build`""
if ($LASTEXITCODE -ne 0) { throw 'SDL3.dll build failed' }
$app = Join-Path $PSScriptRoot 'src\PinyonWheelSetup'
New-Item -ItemType Directory -Force (Join-Path $app 'Native') | Out-Null
Copy-Item (Join-Path $build 'sdl3\SDL3.dll') (Join-Path $app 'Native\SDL3.dll') -Force
if (-not (Test-Path (Join-Path $app 'Assets\App.ico'))) { & (Join-Path $PSScriptRoot 'tools\make-icon.ps1') }
dotnet publish $app -c Release -o $Out
if ($LASTEXITCODE -ne 0) { throw 'publish failed' }
Write-Host "Built $(Join-Path $Out 'PinyonWheelSetup.exe')"
