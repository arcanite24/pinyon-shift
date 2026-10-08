[CmdletBinding()]
param(
    # The adb serial of the device (the launcher passes the one it found).
    [string]$Serial,
    # The PC's state folder, for the v4 title update.
    [string]$StateRoot,
    # The package was built from title update v4: copy the update as well.
    [switch]$TitleUpdateV4,
    [switch]$JsonEvents
)

# The launcher's Install over USB (ONE_CLICK_SETUP_BACKLOG A-5), for a
# device with USB debugging on: installs .local/android/pinyon-shift.apk and
# copies the extracted game (and the v4 update) with tools/pinyon.py android.
# Players without developer options use Share on Wi-Fi instead.

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

try {
    $python = Get-PinyonPython
    $pinyon = Join-Path $PSScriptRoot 'pinyon.py'
    $device = if ($Serial) { @('--serial', $Serial) } else { @() }
    Write-PinyonEvent android 5 'Installing the app over USB.' -JsonEvents:$JsonEvents
    Invoke-PinyonBuildCommand $python (@($pinyon, 'android', 'install') + $device) `
        (Join-Path $logs 'android-usb.log') 'Installing the app over USB failed.' -Step 'Install the app over USB'
    Write-PinyonEvent android 20 'Copying the game files (about 7 GB; an interrupted copy resumes).' -JsonEvents:$JsonEvents
    Invoke-PinyonBuildCommand $python (@($pinyon, 'android', 'push-data') + $device) `
        (Join-Path $logs 'android-usb.log') 'Copying the game files over USB failed.' -Step 'Copy the game files over USB'
    if ($TitleUpdateV4) {
        Write-PinyonEvent android 90 'Copying title update v4.' -JsonEvents:$JsonEvents
        Invoke-PinyonBuildCommand $python (@($pinyon, 'android', 'push-title-update', '--state-root', $StateRoot) + $device) `
            (Join-Path $logs 'android-usb.log') 'Copying title update v4 over USB failed.' -Step 'Copy title update v4 over USB'
    }
    Write-PinyonEvent android 100 'Installed over USB.' -JsonEvents:$JsonEvents
}
catch {
    $failure = $_
    try {
        $errorRecord = New-PinyonFailureRecord -ErrorRecord $failure
        $errorRecord.system = Get-PinyonSystemSummary -Root $root
        [IO.File]::WriteAllText($errorPath, ($errorRecord | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
        foreach ($line in (Format-PinyonFailureRecord -Record $errorRecord -ReportPath '.local\logs\android-error.json')) { [Console]::Out.WriteLine($line) }
    }
    catch {
        [Console]::Out.WriteLine("USB installation failed: $($failure.Exception.Message)")
    }
    [Console]::Out.Flush()
    [Console]::Error.WriteLine("USB installation failed: $($failure.Exception.Message)")
    exit 1
}
