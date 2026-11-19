[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Bootstrapper,
    # Install adds the C++ Build Tools. Repair updates an existing Visual
    # Studio at InstallPath and adds the components it lacks (#393, #339).
    [ValidateSet('Install', 'Repair')] [string]$Mode = 'Install',
    [string]$InstallPath,
    [string[]]$Add = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Bootstrapper -PathType Leaf)) {
    throw "Build Tools bootstrapper is missing: $Bootstrapper"
}

# --passive shows the installer's own progress window without asking anything.
# --wait belongs to the downloaded bootstrapper (vs_buildtools.exe), which
# otherwise returns before the installer finishes. The installed Visual
# Studio Installer (setup.exe) runs the work itself, and from version 4.12
# (Visual Studio 18) its update and modify commands reject --wait with exit
# code 87 (#549; GitHub's windows-latest runners, 2026-11-19).
$common = @('--passive', '--norestart', '--nocache')
if ([IO.Path]::GetFileNameWithoutExtension($Bootstrapper) -ine 'setup') {
    $common = @('--wait') + $common
}
# @() keeps $runs a list of argument lists: a single run assigned straight
# from the if was unrolled into its switches, and the installer was started
# once per switch, in a loop the launcher could not leave (#458, #533).
$runs = @(if ($Mode -eq 'Install') {
    , (@($common) + @('--add', 'Microsoft.VisualStudio.Workload.VCTools', '--includeRecommended'))
} else {
    if ([string]::IsNullOrWhiteSpace($InstallPath)) { throw 'Repair needs the Visual Studio install path.' }
    # powershell -File passes a list as one comma-separated string.
    $components = @($Add | ForEach-Object { $_ -split ',' } | Where-Object { $_ } | ForEach-Object { '--add'; $_.Trim() })
    @(
        , (@('update', '--installPath', $InstallPath) + $common)
        , (@('modify', '--installPath', $InstallPath) + $components + $common)
    )
})
$restart = $false
foreach ($arguments in $runs) {
    $quoted = $arguments | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }
    $process = Start-Process -FilePath $Bootstrapper -ArgumentList $quoted -Wait -PassThru
    if ($process.ExitCode -eq 3010) { $restart = $true }
    # The installer's own code tells the caller why it stopped (a throw here
    # would exit 1 and lose it, #498, #502).
    elseif ($process.ExitCode -ne 0) { exit $process.ExitCode }
}
exit $(if ($restart) { 3010 } else { 0 })
