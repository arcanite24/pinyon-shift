[CmdletBinding()]
param(
    [ValidateRange(1, 32)] [int]$Parallel = [Math]::Max(2, [Math]::Min(16, [Environment]::ProcessorCount - 1)),
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

Write-PinyonEvent build 62 'Building the local code generator.' -JsonEvents:$JsonEvents
Push-Location $sdkRoot
try {
    & $environment.CMake --preset win-amd64 -DREXGLUE_ENABLE_TRACY=OFF
    if ($LASTEXITCODE -ne 0) { throw 'ReXGlue configuration failed.' }
    & $environment.CMake --build --preset win-amd64-release --target rexglue --parallel $Parallel
    if ($LASTEXITCODE -ne 0) { throw 'ReXGlue code-generator build failed.' }
}
finally { Pop-Location }
if (-not (Test-Path -LiteralPath $rexglueExe -PathType Leaf)) {
    throw "The ReXGlue code generator was not produced: $rexglueExe"
}

Write-PinyonEvent build 72 'Translating the verified game code locally.' -JsonEvents:$JsonEvents
if (Test-Path -LiteralPath $generatedRoot) { Remove-Item -LiteralPath $generatedRoot -Recurse -Force }
[void](New-Item -ItemType Directory -Force -Path $generatedRoot)
& $rexglueExe --log-level info --log-file (Join-Path $logs 'codegen.log') codegen $manifest
if ($LASTEXITCODE -ne 0) { throw 'Local code generation failed.' }
foreach ($tree in @('default', 'speech', 'xmedia')) {
    if (-not (Test-Path -LiteralPath (Join-Path $generatedRoot "$tree/sources.cmake") -PathType Leaf)) {
        throw "Generated source tree is incomplete: $tree"
    }
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
$result = [ordered]@{
    schema_version = 1
    created_utc = [DateTime]::UtcNow.ToString('o')
    executable = 'out/build/win-amd64-release/pinyon_shift.exe'
    executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
    generated_locally = $true
}
[IO.File]::WriteAllText($manifestPath, ($result | ConvertTo-Json) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
Write-PinyonEvent build 96 'Local compilation completed successfully.' -JsonEvents:$JsonEvents
$result
