[CmdletBinding()]
param()

# TP-7 (docs/TIME_TO_PLAY_BACKLOG.md): download the pinned tool archives and
# the prebuilt ShiftGlue kit while setup checks and copies the game, so
# provisioning finds them in .local/downloads. Downloads only: nothing is
# installed, nothing asks for administrator rights, and a failure here is
# left for provisioning to retry and report. The destinations are the ones
# provision-toolchain.ps1 and Install-PinyonShiftGlueKit use.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$downloads = Resolve-PinyonLocalPath -RelativePath '.local/downloads'

$llvmZipped = $config.llvm.url -match '\.zip$'
$items = @(
    @{ Tool = 'llvm'; Name = "llvm-$($config.llvm.version)" + $(if ($llvmZipped) { '.zip' } else { '.tar.xz' }) },
    @{ Tool = 'cmake'; Name = "cmake-$($config.cmake.version).zip" },
    @{ Tool = 'ninja'; Name = "ninja-$($config.ninja.version)-win.zip" },
    @{ Tool = 'python'; Name = "python-$($config.python.version)-embed-amd64.zip" },
    @{ Tool = 'extract_xiso'; Name = "extract-xiso-$($config.extract_xiso.version).zip" }
)
# xz unpacks only the upstream .tar.xz LLVM.
if (-not $llvmZipped) { $items += @{ Tool = 'xz'; Name = "xz-$($config.xz.version)-windows.zip" } }

foreach ($item in $items) {
    $tool = $config.($item.Tool)
    if (Test-Path -LiteralPath (Join-Path (Join-Path $root $tool.install_path) $tool.executable) -PathType Leaf) {
        continue
    }
    try {
        Invoke-PinyonDownload -Uri $tool.url -Destination (Join-Path $downloads $item.Name) -Sha256 $tool.sha256
    }
    catch { Write-Warning "Prefetching $($item.Tool) failed: $($_.Exception.Message)" }
}

$kit = Get-PinyonShiftGlueKitEntry
if ($null -ne $kit -and $null -eq (Get-PinyonShiftGlueKitRoot)) {
    try {
        Invoke-PinyonDownload -Uri $kit.url -Sha256 $kit.sha256 -Destination (
            Join-Path $downloads "shiftglue-kit-$($kit.revision.Substring(0, 12))-windows-x64.zip")
    }
    catch { Write-Warning "Prefetching the ShiftGlue kit failed: $($_.Exception.Message)" }
}
