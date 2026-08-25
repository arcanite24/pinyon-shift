[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$IsoPath,

    [string]$ExtractedRoot,

    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$manifestPath = Join-Path $repoRoot 'config/supported-dumps.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$resolvedIso = (Resolve-Path -LiteralPath $IsoPath).Path
$isoInfo = Get-Item -LiteralPath $resolvedIso
$isoHash = (Get-FileHash -LiteralPath $resolvedIso -Algorithm SHA256).Hash.ToUpperInvariant()

$matchedDump = $manifest.dumps | Where-Object {
    [int64]$_.iso.size_bytes -eq $isoInfo.Length -and
    $_.iso.sha256.ToUpperInvariant() -eq $isoHash
} | Select-Object -First 1

if ($null -eq $matchedDump) {
    $failure = [pscustomobject]@{
        recognized = $false
        size_bytes = $isoInfo.Length
        sha256 = $isoHash
        reason = 'No exact size and SHA-256 match in supported-dumps.json.'
    }
    if ($Json) {
        $failure | ConvertTo-Json -Depth 5
    }
    else {
        $failure | Format-List
    }
    exit 1
}

$executableResults = [System.Collections.Generic.List[object]]::new()
if (-not [string]::IsNullOrWhiteSpace($ExtractedRoot)) {
    $resolvedRoot = (Resolve-Path -LiteralPath $ExtractedRoot).Path
    foreach ($executable in $matchedDump.executables) {
        $localPath = Join-Path $resolvedRoot $executable.guest_path
        $exists = Test-Path -LiteralPath $localPath -PathType Leaf
        $actualSize = $null
        $actualHash = $null
        $matches = $false

        if ($exists) {
            $actualInfo = Get-Item -LiteralPath $localPath
            $actualSize = $actualInfo.Length
            $actualHash = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToUpperInvariant()
            $matches = $actualSize -eq [int64]$executable.size_bytes -and
                       $actualHash -eq $executable.sha256.ToUpperInvariant()
        }

        $executableResults.Add([pscustomobject]@{
            guest_path = $executable.guest_path
            role = $executable.role
            exists = $exists
            matches = $matches
            size_bytes = $actualSize
            sha256 = $actualHash
        })
    }
}

$allExecutablesMatch = $executableResults.Count -eq 0 -or
    @($executableResults | Where-Object { -not $_.matches }).Count -eq 0

$result = [pscustomobject]@{
    recognized = $true
    dump_id = $matchedDump.id
    status = $matchedDump.status
    title_id = $matchedDump.title_id
    serial = $matchedDump.serial
    iso_size_bytes = $isoInfo.Length
    iso_sha256 = $isoHash
    extracted_executables_checked = $executableResults.Count
    extracted_executables_match = $allExecutablesMatch
    executables = @($executableResults)
}

if ($Json) {
    $result | ConvertTo-Json -Depth 6
}
else {
    $result | Format-List recognized, dump_id, status, title_id, serial, iso_size_bytes,
        iso_sha256, extracted_executables_checked, extracted_executables_match
    if ($executableResults.Count -ne 0) {
        $executableResults | Format-Table guest_path, role, exists, matches, size_bytes -AutoSize
    }
}

if (-not $allExecutablesMatch) {
    exit 1
}
