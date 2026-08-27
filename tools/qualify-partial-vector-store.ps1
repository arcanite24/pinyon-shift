[CmdletBinding()]
param(
    [string]$ReportPath,
    [ValidateRange(1, 4096)] [int]$RandomIterations = 256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$git = Get-PinyonGit
$sdkRoot = Resolve-PinyonLocalPath -RelativePath $config.rexglue.path
$testExe = Join-Path $sdkRoot 'out/win-amd64/Release/ppc_tests.exe'
$generatedRoot = Join-Path $sdkRoot 'out/build/win-amd64/tests/ppc/generated'
$patchMarkerPath = Join-Path $sdkRoot '.pinyon-patches.json'

foreach ($required in @($testExe, $patchMarkerPath,
        (Join-Path $generatedRoot 'ppc_test_functions.cpp'),
        (Join-Path $generatedRoot 'ppc_test_cases.cpp'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Partial-vector-store qualification requires: $required"
    }
}

if ($RandomIterations -ne 256) {
    throw 'The generated regression harness currently uses exactly 256 iterations per instruction.'
}

$filter = '[instr_partial_vector_store],[partial_vector_store]'
$testOutput = (& $testExe $filter --reporter compact 2>&1 | Out-String).Trim()
$testExitCode = $LASTEXITCODE
$summaryMatch = [regex]::Match($testOutput,
    'All tests passed \((?<assertions>[0-9]+) assertions in (?<cases>[0-9]+) test cases\)')
$passed = $testExitCode -eq 0 -and $summaryMatch.Success

$patchMarker = Get-Content -LiteralPath $patchMarkerPath -Raw | ConvertFrom-Json
$sourceCommit = (& $git -C $root rev-parse HEAD).Trim().ToLowerInvariant()
$sourceDirty = @(& $git -C $root status --porcelain).Count -ne 0
$rexglueCommit = (& $git -C $sdkRoot rev-parse HEAD).Trim().ToLowerInvariant()
$compilerPath = Join-Path (Join-Path $root $config.llvm.install_path) 'bin/clang++.exe'
$compilerVersion = (& $compilerPath --version | Select-Object -First 1)
$generatedFunctionsPath = Join-Path $generatedRoot 'ppc_test_functions.cpp'
$generatedTestsPath = Join-Path $generatedRoot 'ppc_test_cases.cpp'

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $reportsRoot = Resolve-PinyonLocalPath -RelativePath '.local/reports'
    [void](New-Item -ItemType Directory -Force -Path $reportsRoot)
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $ReportPath = Join-Path $reportsRoot "partial-vector-store-qualification-$stamp.json"
} else {
    $ReportPath = [IO.Path]::GetFullPath($ReportPath)
    [void](New-Item -ItemType Directory -Force -Path (Split-Path $ReportPath -Parent))
}

$report = [ordered]@{
    schema = 'pinyon-shift.partial-vector-store-qualification.v1'
    created_utc = [DateTime]::UtcNow.ToString('o')
    passed = $passed
    suite = [ordered]@{
        filter = $filter
        deterministic_offsets = @(0, 1, 4, 8, 12, 15)
        random_seed = '0x5EED07A1'
        random_iterations_per_instruction = $RandomIterations
        test_cases = if ($summaryMatch.Success) { [int]$summaryMatch.Groups['cases'].Value } else { 0 }
        assertions = if ($summaryMatch.Success) { [int]$summaryMatch.Groups['assertions'].Value } else { 0 }
        output = $testOutput
    }
    provenance = [ordered]@{
        pinyon_shift_commit = $sourceCommit
        pinyon_shift_dirty = $sourceDirty
        rexglue_base_commit = $rexglueCommit
        rexglue_patch_set_sha256 = (Get-FileHash -LiteralPath $patchMarkerPath -Algorithm SHA256).Hash
        ordered_patches = @($patchMarker.patches | ForEach-Object {
            [ordered]@{ name = $_.name; sha256 = $_.sha256 }
        })
        generated_functions_sha256 = (Get-FileHash -LiteralPath $generatedFunctionsPath -Algorithm SHA256).Hash
        generated_tests_sha256 = (Get-FileHash -LiteralPath $generatedTestsPath -Algorithm SHA256).Hash
        test_executable_sha256 = (Get-FileHash -LiteralPath $testExe -Algorithm SHA256).Hash
        compiler = $compilerVersion
        renderer = 'not_applicable_cpu_semantics'
        gpu_driver = 'not_applicable_cpu_semantics'
        config_schema = 8
        effective_settings = 'not_applicable_generated_cpu_test'
    }
}

[IO.File]::WriteAllText($ReportPath, ($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
$report

if (-not $passed) {
    throw "Partial-vector-store qualification failed. Report: $ReportPath"
}
