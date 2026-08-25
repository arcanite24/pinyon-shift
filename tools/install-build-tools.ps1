[CmdletBinding()]
param([Parameter(Mandatory)] [string]$Bootstrapper)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Bootstrapper -PathType Leaf)) {
    throw "Build Tools bootstrapper is missing: $Bootstrapper"
}

$arguments = @(
    '--quiet', '--wait', '--norestart', '--nocache',
    '--add', 'Microsoft.VisualStudio.Workload.VCTools',
    '--includeRecommended'
)
$process = Start-Process -FilePath $Bootstrapper -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -notin @(0, 3010)) {
    throw "Microsoft C++ Build Tools installation failed with exit code $($process.ExitCode)."
}
exit $process.ExitCode
