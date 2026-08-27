Set-StrictMode -Version Latest

function Get-PinyonRepoRoot {
    (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-PinyonReleaseToolchain {
    $root = Get-PinyonRepoRoot
    Get-Content -LiteralPath (Join-Path $root 'config/release-toolchain.json') -Raw |
        ConvertFrom-Json
}

function Write-PinyonEvent {
    param(
        [Parameter(Mandatory)] [string]$Stage,
        [Parameter(Mandatory)] [ValidateRange(0, 100)] [int]$Percent,
        [Parameter(Mandatory)] [string]$Message,
        [switch]$JsonEvents
    )
    if ($JsonEvents) {
        $event = [ordered]@{ stage = $Stage; percent = $Percent; message = $Message }
        Write-Output ('::pinyon::' + ($event | ConvertTo-Json -Compress))
    }
    else {
        Write-Host "[$($Stage.ToUpperInvariant())] $Message"
    }
}

function Resolve-PinyonLocalPath {
    param([Parameter(Mandatory)] [string]$RelativePath)
    $root = Get-PinyonRepoRoot
    $full = [IO.Path]::GetFullPath((Join-Path $root $RelativePath))
    $local = [IO.Path]::GetFullPath((Join-Path $root '.local'))
    $prefix = $local.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use a release-work path outside $local"
    }
    $full
}

function Invoke-PinyonDownload {
    param(
        [Parameter(Mandatory)] [string]$Uri,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$Sha256
    )
    $parent = Split-Path $Destination -Parent
    [void](New-Item -ItemType Directory -Force -Path $parent)
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
        if ($actual -eq $Sha256) { return }
        Remove-Item -LiteralPath $Destination -Force
    }
    $partial = "$Destination.partial"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    try {
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($null -ne $curl) {
            & $curl.Source --fail --location --retry 3 --output $partial $Uri
            if ($LASTEXITCODE -ne 0) { throw "Download failed: $Uri" }
        }
        else {
            Invoke-WebRequest -Uri $Uri -OutFile $partial -UseBasicParsing
        }
        $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash
        if ($actual -ne $Sha256) {
            throw "Downloaded file failed SHA-256 verification. Expected $Sha256; got $actual."
        }
        Move-Item -LiteralPath $partial -Destination $Destination
    }
    finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}

function Expand-PinyonTarXz {
    param(
        [Parameter(Mandatory)] [string]$Archive,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$XzPath
    )
    $archive = [IO.Path]::GetFullPath($Archive)
    $destination = [IO.Path]::GetFullPath($Destination)
    $xzPath = [IO.Path]::GetFullPath($XzPath)
    $tarArchive = Join-Path (Split-Path $archive -Parent) `
        ([IO.Path]::GetFileNameWithoutExtension($archive))
    if (-not $archive.EndsWith('.tar.xz', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Expected a .tar.xz archive: $archive"
    }
    if (-not (Test-Path -LiteralPath $xzPath -PathType Leaf)) {
        throw "The pinned XZ extractor is missing: $xzPath"
    }
    if (Test-Path -LiteralPath $tarArchive) {
        Remove-Item -LiteralPath $tarArchive -Force
    }
    try {
        & $xzPath --decompress --keep --force -- $archive
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $tarArchive -PathType Leaf)) {
            throw 'Unable to decompress the LLVM toolchain archive.'
        }
        & tar.exe -xf $tarArchive -C $destination
        if ($LASTEXITCODE -ne 0) { throw 'Unable to extract the LLVM toolchain.' }
    }
    finally {
        if (Test-Path -LiteralPath $tarArchive) {
            Remove-Item -LiteralPath $tarArchive -Force
        }
    }
}

function Get-PinyonVisualStudioRoot {
    param([switch]$AllowMissing)
    $config = Get-PinyonReleaseToolchain
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $root = $null
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $root = & $vswhere -latest -products * -requires $config.visual_studio.required_component `
            -property installationPath | Select-Object -First 1
    }
    if ([string]::IsNullOrWhiteSpace($root) -and -not $AllowMissing) {
        throw 'Microsoft C++ Build Tools were not found.'
    }
    $root
}

function ConvertTo-PinyonCommandPath {
    param([AllowEmptyString()] [string]$PathValue)

    $entries = @($PathValue -split ';' | ForEach-Object {
        $entry = $_.Trim()
        if ($entry.Length -ge 2 -and $entry.StartsWith('"') -and $entry.EndsWith('"')) {
            $entry = $entry.Substring(1, $entry.Length - 2).Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($entry)) { $entry }
    })
    $entries -join ';'
}

function Enter-PinyonBuildEnvironment {
    $root = Get-PinyonRepoRoot
    $config = Get-PinyonReleaseToolchain
    $vsRoot = Get-PinyonVisualStudioRoot
    $devCmd = Join-Path $vsRoot 'Common7/Tools/VsDevCmd.bat'
    $inheritedPath = $env:PATH
    try {
        # Quoted PATH entries containing parentheses break VsDevCmd's batch parser.
        $env:PATH = ConvertTo-PinyonCommandPath -PathValue $inheritedPath
        $lines = @(& $env:ComSpec /d /s /c "`"$devCmd`" -arch=x64 -host_arch=x64 >nul && set")
    }
    finally {
        $env:PATH = $inheritedPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize the Microsoft x64 build environment.' }
    foreach ($line in $lines) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) {
            [Environment]::SetEnvironmentVariable($line.Substring(0, $separator),
                $line.Substring($separator + 1), 'Process')
        }
    }
    $llvm = [IO.Path]::GetFullPath((Join-Path $root $config.llvm.install_path))
    $env:PATH = "$(Join-Path $llvm 'bin');$env:PATH"
    [pscustomobject]@{
        VisualStudioRoot = $vsRoot
        CMake = Join-Path $vsRoot 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
        Ninja = Join-Path $vsRoot 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
        LlvmRoot = $llvm
    }
}

function Get-PinyonGit {
    $root = Get-PinyonRepoRoot
    $config = Get-PinyonReleaseToolchain
    $candidate = Join-Path (Join-Path $root $config.git.install_path) $config.git.executable
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw 'Git is not available. Run provision-toolchain.ps1 first.'
    }
    $candidate
}
