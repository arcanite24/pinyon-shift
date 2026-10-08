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
$common = @('--passive', '--wait', '--norestart', '--nocache')
$runs = if ($Mode -eq 'Install') {
    , (@($common) + @('--add', 'Microsoft.VisualStudio.Workload.VCTools', '--includeRecommended'))
} else {
    if ([string]::IsNullOrWhiteSpace($InstallPath)) { throw 'Repair needs the Visual Studio install path.' }
    # powershell -File passes a list as one comma-separated string.
    $components = @($Add | ForEach-Object { $_ -split ',' } | Where-Object { $_ } | ForEach-Object { '--add'; $_.Trim() })
    @(
        , (@('update', '--installPath', $InstallPath) + $common)
        , (@('modify', '--installPath', $InstallPath) + $components + $common)
    )
}
$restart = $false
foreach ($arguments in $runs) {
    $quoted = $arguments | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }
    $process = Start-Process -FilePath $Bootstrapper -ArgumentList $quoted -Wait -PassThru
    if ($process.ExitCode -eq 3010) { $restart = $true }
    elseif ($process.ExitCode -ne 0) {
        throw "Microsoft C++ Build Tools $($Mode.ToLowerInvariant()) failed with exit code $($process.ExitCode)."
    }
}
exit $(if ($restart) { 3010 } else { 0 })
