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
    $elevated = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -Wait -PassThru
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

$environment = Enter-PinyonBuildEnvironment
$git = Get-PinyonGit
foreach ($required in @(
    @{ Name = 'Git'; Path = $git },
    @{ Name = 'XZ'; Path = $xzExe },
    @{ Name = 'CMake'; Path = $environment.CMake },
    @{ Name = 'Ninja'; Path = $environment.Ninja },
    @{ Name = 'LLVM'; Path = $llvmExe },
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
    extract_xiso = $extractExe
}
