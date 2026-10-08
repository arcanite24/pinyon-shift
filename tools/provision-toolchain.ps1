[CmdletBinding()]
param([switch]$JsonEvents)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$downloads = Resolve-PinyonLocalPath -RelativePath '.local/downloads'
[void](New-Item -ItemType Directory -Force -Path $downloads)

Write-PinyonEvent tools 18 'Checking the Windows build environment.' -JsonEvents:$JsonEvents
$vsRoot = Get-PinyonVisualStudioRoot -AllowMissing
# Only the hosts of downloads still to come: a provisioned PC builds offline.
$pending = @(foreach ($name in 'git', 'xz', 'llvm', 'extract_xiso', 'python', 'cmake', 'ninja') {
    $tool = $config.$name
    if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $root $tool.install_path) $tool.executable) -PathType Leaf)) {
        $tool.url
    }
})
if ([string]::IsNullOrWhiteSpace($vsRoot)) { $pending += $config.visual_studio.bootstrap_url }
if (-not (Test-Path -LiteralPath (Join-Path (Resolve-PinyonRexGlueRoot) 'CMakeLists.txt') -PathType Leaf)) {
    $pending += $config.rexglue.repository
}
Assert-PinyonDownloadHosts -Uris $pending
if ([string]::IsNullOrWhiteSpace($vsRoot)) {
    Write-PinyonEvent tools 20 'Microsoft C++ Build Tools are required. Windows may ask for administrator permission.' -JsonEvents:$JsonEvents
    $bootstrap = Join-Path $downloads 'vs_BuildTools.exe'
    if (-not (Test-Path -LiteralPath $bootstrap -PathType Leaf)) {
        $partial = "$bootstrap.partial"
        Invoke-WebRequest -Uri $config.visual_studio.bootstrap_url -OutFile $partial -UseBasicParsing
        Move-Item -LiteralPath $partial -Destination $bootstrap -Force
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $bootstrap
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Subject -notlike "*$($config.visual_studio.bootstrap_signer)*") {
        Remove-Item -LiteralPath $bootstrap -Force
        throw 'The Microsoft Build Tools installer signature is invalid.'
    }
    $helper = Join-Path $PSScriptRoot 'install-build-tools.ps1'
    $arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$helper`" -Bootstrapper `"$bootstrap`""
    # The running PowerShell by its own path, since PATH may not hold it. Process.Start keeps
    # the Win32 error that Start-Process drops, so a declined permission prompt
    # (ERROR_CANCELLED) can be told apart from a failed installer.
    $startInfo = [Diagnostics.ProcessStartInfo]::new((Get-Process -Id $PID).Path, $arguments)
    $startInfo.Verb = 'runas'
    $startInfo.UseShellExecute = $true
    try {
        $elevated = [Diagnostics.Process]::Start($startInfo)
    }
    catch {
        $win32 = $_.Exception.InnerException -as [ComponentModel.Win32Exception]
        if ($null -ne $win32 -and $win32.NativeErrorCode -eq 1223) {
            throw ('Windows administrator permission was declined, so the Microsoft C++ Build Tools ' +
                'were not installed. The build needs them: start the build again and choose Yes when ' +
                'Windows asks for permission.')
        }
        throw
    }
    $elevated.WaitForExit()
    if ($elevated.ExitCode -notin @(0, 3010)) {
        throw "Microsoft C++ Build Tools installation stopped with exit code $($elevated.ExitCode)."
    }
    $vsRoot = Get-PinyonVisualStudioRoot
}

Write-PinyonEvent tools 23 'Preparing Git.' -JsonEvents:$JsonEvents
$gitRoot = [IO.Path]::GetFullPath((Join-Path $root $config.git.install_path))
$gitExe = Join-Path $gitRoot $config.git.executable
if (-not (Test-Path -LiteralPath $gitExe -PathType Leaf)) {
    $archive = Join-Path $downloads "mingit-$($config.git.version).zip"
    Invoke-PinyonDownload -Uri $config.git.url -Destination $archive -Sha256 $config.git.sha256
    [void](New-Item -ItemType Directory -Force -Path $gitRoot)
    Expand-Archive -LiteralPath $archive -DestinationPath $gitRoot -Force
}

Write-PinyonEvent tools 26 'Preparing the pinned LLVM compiler.' -JsonEvents:$JsonEvents
$xzRoot = [IO.Path]::GetFullPath((Join-Path $root $config.xz.install_path))
$xzExe = Join-Path $xzRoot $config.xz.executable
if (-not (Test-Path -LiteralPath $xzExe -PathType Leaf)) {
    $archive = Join-Path $downloads "xz-$($config.xz.version)-windows.zip"
    Invoke-PinyonDownload -Uri $config.xz.url -Destination $archive -Sha256 $config.xz.sha256
    if (Test-Path -LiteralPath $xzRoot) { Remove-Item -LiteralPath $xzRoot -Recurse -Force }
    [void](New-Item -ItemType Directory -Force -Path $xzRoot)
    Expand-Archive -LiteralPath $archive -DestinationPath $xzRoot -Force
}

$llvmRoot = [IO.Path]::GetFullPath((Join-Path $root $config.llvm.install_path))
$llvmExe = Join-Path $llvmRoot $config.llvm.executable
if (-not (Test-Path -LiteralPath $llvmExe -PathType Leaf)) {
    $archive = Join-Path $downloads "llvm-$($config.llvm.version).tar.xz"
    Invoke-PinyonDownload -Uri $config.llvm.url -Destination $archive -Sha256 $config.llvm.sha256
    $staging = Resolve-PinyonLocalPath -RelativePath ".local/toolchain/llvm-$($config.llvm.version)-staging"
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    [void](New-Item -ItemType Directory -Force -Path $staging)
    Expand-PinyonTarXz -Archive $archive -Destination $staging -XzPath $xzExe
    $children = @(Get-ChildItem -LiteralPath $staging -Directory)
    if ($children.Count -ne 1) { throw 'The LLVM archive layout is not recognized.' }
    if (Test-Path -LiteralPath $llvmRoot) { Remove-Item -LiteralPath $llvmRoot -Recurse -Force }
    Move-Item -LiteralPath $children[0].FullName -Destination $llvmRoot
    Remove-Item -LiteralPath $staging -Recurse -Force
}

Write-PinyonEvent tools 29 'Preparing the disc-image extractor.' -JsonEvents:$JsonEvents
$extractRoot = [IO.Path]::GetFullPath((Join-Path $root $config.extract_xiso.install_path))
$extractExe = Join-Path $extractRoot $config.extract_xiso.executable
if (-not (Test-Path -LiteralPath $extractExe -PathType Leaf)) {
    $archive = Join-Path $downloads "extract-xiso-$($config.extract_xiso.version).zip"
    Invoke-PinyonDownload -Uri $config.extract_xiso.url -Destination $archive `
        -Sha256 $config.extract_xiso.sha256
    [void](New-Item -ItemType Directory -Force -Path $extractRoot)
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
}

Write-PinyonEvent tools 30 'Preparing the local shader tooling runtime.' -JsonEvents:$JsonEvents
$pythonRoot = Resolve-PinyonLocalPath -RelativePath $config.python.install_path
$pythonExe = Join-Path $pythonRoot $config.python.executable
$pythonCheck = "import hashlib, json, struct, subprocess, tomllib, zipfile; assert hasattr(hashlib, 'file_digest')"
$pythonReady = $false
if (Test-Path -LiteralPath $pythonExe -PathType Leaf) {
    & $pythonExe -I -c $pythonCheck
    $pythonReady = $LASTEXITCODE -eq 0
}
if (-not $pythonReady) {
    $archive = Join-Path $downloads "python-$($config.python.version)-embed-amd64.zip"
    Invoke-PinyonDownload -Uri $config.python.url -Destination $archive -Sha256 $config.python.sha256
    [void](New-Item -ItemType Directory -Force -Path $pythonRoot)
    Expand-Archive -LiteralPath $archive -DestinationPath $pythonRoot -Force
}
& $pythonExe -I -c $pythonCheck
if ($LASTEXITCODE -ne 0) { throw 'The local Python runtime failed its shader tooling check.' }

Write-PinyonEvent tools 31 'Preparing CMake with support for the build presets.' -JsonEvents:$JsonEvents
$cmakeRoot = Resolve-PinyonLocalPath -RelativePath $config.cmake.install_path
if (-not (Test-Path -LiteralPath (Join-Path $cmakeRoot $config.cmake.executable) -PathType Leaf)) {
    $archive = Join-Path $downloads "cmake-$($config.cmake.version).zip"
    Invoke-PinyonDownload -Uri $config.cmake.url -Destination $archive -Sha256 $config.cmake.sha256
    Expand-Archive -LiteralPath $archive -DestinationPath (Split-Path $cmakeRoot -Parent) -Force
}
# Ninja is pinned like CMake, so the build does not depend on the Visual
# Studio CMake component being installed.
$ninjaRoot = Resolve-PinyonLocalPath -RelativePath $config.ninja.install_path
if (-not (Test-Path -LiteralPath (Join-Path $ninjaRoot $config.ninja.executable) -PathType Leaf)) {
    $archive = Join-Path $downloads "ninja-$($config.ninja.version)-win.zip"
    Invoke-PinyonDownload -Uri $config.ninja.url -Destination $archive -Sha256 $config.ninja.sha256
    [void](New-Item -ItemType Directory -Force -Path $ninjaRoot)
    Expand-Archive -LiteralPath $archive -DestinationPath $ninjaRoot -Force
}
$environment = Enter-PinyonBuildEnvironment
$git = Get-PinyonGit
foreach ($required in @(
    @{ Name = 'Git'; Path = $git },
    @{ Name = 'XZ'; Path = $xzExe },
    @{ Name = 'CMake'; Path = $environment.CMake },
    @{ Name = 'Ninja'; Path = $environment.Ninja },
    @{ Name = 'LLVM'; Path = $llvmExe },
    @{ Name = 'Python'; Path = $pythonExe },
    @{ Name = 'extract-xiso'; Path = $extractExe }
)) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType Leaf)) {
        throw "$($required.Name) was not provisioned correctly: $($required.Path)"
    }
}
Write-PinyonEvent tools 32 'Windows build tools are ready.' -JsonEvents:$JsonEvents

[pscustomobject]@{
    result = 'pass'
    git = $git
    cmake = $environment.CMake
    ninja = $environment.Ninja
    llvm = $llvmExe
    python = $pythonExe
    extract_xiso = $extractExe
}
