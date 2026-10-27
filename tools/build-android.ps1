[CmdletBinding()]
param(
    # The player accepted the Android SDK license (the launcher shows it
    # first); without it, missing SDK packages stop the build with a hint.
    [switch]$AcceptAndroidLicenses,
    [int]$Parallel = 0,
    # Build the package from the v4 title update's code (tools/build-v4.ps1
    # generated it when the player chose v4 in the launcher).
    [switch]$TitleUpdateV4,
    [switch]$JsonEvents
)

# Builds .local/android/pinyon-shift.apk from the game this PC already built
# (tools/pinyon.py android build), for the launcher's Build Android APK
# action. A PC without an Android SDK or JDK gets the pinned command-line
# tools and Temurin JDK from config/android-toolchain.json under
# .local/toolchain; nothing outside the install folder changes.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$logs = Resolve-PinyonLocalPath -RelativePath '.local/logs'
[void](New-Item -ItemType Directory -Force -Path $logs)
$errorPath = Join-Path $logs 'android-error.json'
if (Test-Path -LiteralPath $errorPath) { Remove-Item -LiteralPath $errorPath -Force }

function Find-PinyonAndroidSdk {
    param([Parameter(Mandatory)] [string]$LocalSdk)
    $candidates = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT)
    if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
    $candidates += Join-Path $HOME 'Android\Sdk'
    $candidates += $LocalSdk
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'platform-tools'))) {
            return $candidate
        }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate 'cmdline-tools\latest\bin'))) {
            return $candidate
        }
    }
    $null
}

function Test-PinyonJdk {
    param(
        [Parameter(Mandatory)] [string]$JavaHome,
        [Parameter(Mandatory)] [int]$MinimumMajor
    )
    $javac = Join-Path $JavaHome 'bin\javac.exe'
    if (-not (Test-Path -LiteralPath $javac -PathType Leaf)) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\keytool.exe') -PathType Leaf)) { return $false }
    try {
        # javac prints its version on stdout (newer) or stderr (older).
        $text = (& $javac -version 2>&1 | Out-String)
    }
    catch { return $false }
    if ($text -notmatch 'javac\s+(?:1\.)?(\d+)') { return $false }
    [int]$Matches[1] -ge $MinimumMajor
}

try {
    $android = Get-Content -LiteralPath (Join-Path $root 'config/android-toolchain.json') -Raw |
        ConvertFrom-Json
    $bootstrap = $android.bootstrap

    Write-PinyonEvent android 2 'Checking the PC build the Android package is made from.' -JsonEvents:$JsonEvents
    $generated = if ($TitleUpdateV4) { '.local/generated-v4' } else { '.local/generated' }
    if (-not (Test-Path -LiteralPath (Join-Path $root "$generated/default/sources.cmake") -PathType Leaf)) {
        if ($TitleUpdateV4) {
            throw 'The v4 game has not been built on this PC yet. Turn on v4 in the DLC panel and play once, then build the Android package.'
        }
        throw 'The game has not been built on this PC yet. Build and play it once, then build the Android package.'
    }
    Assert-PinyonFreeSpace -Root $root -Android
    $python = Get-PinyonPython
    $pinyon = Join-Path $PSScriptRoot 'pinyon.py'
    $env:PINYON_REXSDK_DIR = Resolve-PinyonRexGlueRoot
    # CMake clones the FidelityFX SDK with git (#810), and most players have
    # none: use the pinned MinGit the PC build already provisioned.
    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        $git = Get-PinyonGit
        $env:PATH = "$(Split-Path $git -Parent);$env:PATH"
    }

    Write-PinyonEvent android 5 'Checking the Android SDK, NDK and JDK.' -JsonEvents:$JsonEvents
    $doctorLog = Join-Path $logs 'android-doctor.log'
    Invoke-PinyonLoggedCommand -FilePath $python -Arguments @($pinyon, 'android', 'doctor') `
        -LogPath $doctorLog | Out-Host
    if ($LASTEXITCODE -ne 0) {
        # The SDK packages come from Google; the JDK and command-line tools
        # too when this PC has none. Named up front if a site is blocked.
        Assert-PinyonDownloadHosts -Uris @($bootstrap.jdk.url, $bootstrap.cmdline_tools.url, 'https://dl.google.com/')
        # A JDK 17 or newer for sdkmanager, javac and keytool. One that is
        # too old (Oracle's Java 8 on PATH: "Java version 17 or higher is
        # required", #811) or that lacks keytool (Oracle's javapath shim, #868)
        # does not count.
        $localJdk = Resolve-PinyonLocalPath -RelativePath $bootstrap.jdk.install_path
        $jdkHome = $null
        $onPath = Get-Command javac.exe -ErrorAction SilentlyContinue
        $pathHome = if ($onPath) { Split-Path (Split-Path $onPath.Source -Parent) -Parent } else { $null }
        foreach ($candidate in @($env:JAVA_HOME, $localJdk, $pathHome)) {
            if ($candidate -and (Test-PinyonJdk -JavaHome $candidate -MinimumMajor $android.jdk_major)) {
                $jdkHome = $candidate
                break
            }
        }
        if (-not $jdkHome) {
            Write-PinyonEvent android 8 "Downloading the Temurin JDK $($bootstrap.jdk.version) (about 190 MB)." -JsonEvents:$JsonEvents
            $archive = Resolve-PinyonLocalPath -RelativePath ".local/downloads/$(Split-Path $bootstrap.jdk.url -Leaf)"
            Invoke-PinyonDownload -Uri $bootstrap.jdk.url -Destination $archive -Sha256 $bootstrap.jdk.sha256
            $toolchain = Split-Path $localJdk -Parent
            Expand-PinyonZip -Archive $archive -Destination $toolchain
            if (-not (Test-PinyonJdk -JavaHome $localJdk -MinimumMajor $android.jdk_major)) {
                throw "The JDK archive did not unpack to a working JDK in $localJdk."
            }
            $jdkHome = $localJdk
        }
        # Replaces an old or partial JAVA_HOME for this build only.
        $env:JAVA_HOME = $jdkHome

        # The pinned sdkmanager installs the pinned NDK, build tools and
        # platform, into the PC's existing SDK when it has one. Android
        # Studio's newer command-line tools replace sdkmanager with a shim that
        # split "ndk;29.0.14206865" into two unknown packages (#567).
        $localSdk = Resolve-PinyonLocalPath -RelativePath $bootstrap.android_sdk_path
        $sdk = Find-PinyonAndroidSdk -LocalSdk $localSdk
        if (-not $sdk) { $sdk = $localSdk }
        $sdkmanager = Join-Path $localSdk 'cmdline-tools\latest\bin\sdkmanager.bat'
        if (-not (Test-Path -LiteralPath $sdkmanager)) {
            Write-PinyonEvent android 12 'Downloading the Android SDK command-line tools (about 150 MB).' -JsonEvents:$JsonEvents
            $archive = Resolve-PinyonLocalPath -RelativePath ".local/downloads/$(Split-Path $bootstrap.cmdline_tools.url -Leaf)"
            Invoke-PinyonDownload -Uri $bootstrap.cmdline_tools.url -Destination $archive `
                -Sha256 $bootstrap.cmdline_tools.sha256
            $unpack = Join-Path $localSdk 'cmdline-tools\unpack'
            Remove-PinyonTree -Path $unpack
            Expand-PinyonZip -Archive $archive -Destination $unpack
            $latest = Join-Path $localSdk 'cmdline-tools\latest'
            Remove-PinyonTree -Path $latest
            # One rename of a short path, whatever depth lies below it.
            [IO.Directory]::Move((Join-Path $unpack 'cmdline-tools'), $latest)
            Remove-PinyonTree -Path $unpack
        }
        $env:ANDROID_HOME = $sdk
        $env:ANDROID_SDK_ROOT = $sdk

        if (-not $AcceptAndroidLicenses) {
            $failure = [Exception]::new('Installing the Android NDK, build tools and platform needs the Android SDK license to be accepted.')
            $failure.Data['step'] = 'Install the Android SDK packages'
            $failure.Data['hint'] = "Accept the Android SDK license ($($bootstrap.cmdline_tools.license_url)) when the launcher asks, or run: python tools/pinyon.py android doctor --install"
            throw $failure
        }
        Write-PinyonEvent android 18 'Installing the Android NDK, build tools and platform (a few GB, once).' -JsonEvents:$JsonEvents
        Invoke-PinyonBuildCommand $python @($pinyon, 'android', 'doctor', '--install', '--accept-licenses') `
            (Join-Path $logs 'android-sdk-install.log') 'Installing the Android SDK packages failed.' `
            -Step 'Install the Android SDK packages'
    }

    if ($Parallel -le 0) { $Parallel = Get-PinyonBuildJobCount }
    Write-PinyonEvent android 30 'Compiling the game for Android. The first build takes 20 to 60 minutes.' -JsonEvents:$JsonEvents
    $buildArguments = @($pinyon, 'android', 'build', '--jobs', "$Parallel")
    if ($TitleUpdateV4) { $buildArguments += '--title-update-v4' }
    Invoke-PinyonBuildCommand $python $buildArguments `
        (Join-Path $logs 'android-build.log') 'The Android build failed.' -Step 'Build the Android package'

    $apk = Join-Path $root '.local\android\pinyon-shift.apk'
    if (-not (Test-Path -LiteralPath $apk -PathType Leaf)) {
        throw 'The Android build completed without producing pinyon-shift.apk.'
    }
    # What the package holds, for the launcher's Android panel.
    $record = [ordered]@{
        schema_version = 1
        title_update_v4 = [bool]$TitleUpdateV4
        built_utc = [DateTime]::UtcNow.ToString('o')
        bytes = (Get-Item -LiteralPath $apk).Length
    }
    [IO.File]::WriteAllText((Join-Path $root '.local\android\pinyon-shift.json'),
        ($record | ConvertTo-Json) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-PinyonEvent android 100 "Android package ready: $apk" -JsonEvents:$JsonEvents
}
catch {
    # As setup-preview.ps1 reports: plain text, a JSON record the launcher
    # reads, and an exit code.
    $failure = $_
    try {
        $errorRecord = New-PinyonFailureRecord -ErrorRecord $failure
        $errorRecord.system = Get-PinyonSystemSummary -Root $root
        [IO.File]::WriteAllText($errorPath, ($errorRecord | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
        foreach ($line in (Format-PinyonFailureRecord -Record $errorRecord -ReportPath '.local\logs\android-error.json')) { [Console]::Out.WriteLine($line) }
        [Console]::Out.WriteLine("Failure details: $errorPath")
    }
    catch {
        [Console]::Out.WriteLine("Android build failed: $($failure.Exception.Message)")
        [Console]::Out.WriteLine("The failure report could not be written: $($_.Exception.Message)")
    }
    [Console]::Out.Flush()
    [Console]::Error.WriteLine("Android build failed: $($failure.Exception.Message)")
    exit 1
}
