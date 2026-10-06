[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateNotNullOrEmpty()] [string]$ExtractedRoot,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-ExtractedFileSha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '') }
    finally { $hasher.Dispose(); $stream.Dispose() }
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'config/supported-dumps.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$resolvedRoot = (Resolve-Path -LiteralPath $ExtractedRoot).Path
$rootInfo = Get-Item -LiteralPath $resolvedRoot
if (-not $rootInfo.PSIsContainer -or ($rootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Choose a real extracted game directory, without links or junctions.'
}
$prefix = $resolvedRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$files = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
$pending = [Collections.Generic.Queue[string]]::new()
$pending.Enqueue($resolvedRoot)
while ($pending.Count -gt 0) {
    foreach ($item in Get-ChildItem -LiteralPath $pending.Dequeue() -Force) {
        $relative = $item.FullName.Substring($prefix.Length).Replace('\', '/')
        # The disc's system update is not part of the extracted game input.
        if ($relative -eq '$SystemUpdate') { continue }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Linked game input is unsupported: $relative"
        }
        if ($item.PSIsContainer) { $pending.Enqueue($item.FullName) }
        else { $files.Add($relative, $item) }
    }
}

$matchedDump = $null
$mismatches = [Collections.Generic.List[string]]::new()
foreach ($dump in $manifest.dumps) {
    $catalogProperty = $dump.extraction.PSObject.Properties['file_catalog']
    if ($null -eq $catalogProperty) { continue }
    $catalogPath = Join-Path (Join-Path $repoRoot 'config') $catalogProperty.Value
    $catalog = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($catalog.schema_version -ne 1 -or $catalog.dump_id -ne $dump.id -or
        $catalog.files.Count -ne [int]$dump.extraction.file_count -or
        $catalog.iso_sha256 -ne $dump.iso.sha256) {
        throw 'The extracted-file catalog does not match the supported dump manifest.'
    }
    $mismatches.Clear()
    if ($files.Count -ne $catalog.files.Count) { $mismatches.Add('The game file count does not match.') }
    foreach ($expected in $catalog.files) {
        $relative = [string]$expected.guest_path
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.([/\\]|$)') {
            throw 'Invalid relative path in the extracted-file catalog.'
        }
        $actual = $null
        if (-not $files.TryGetValue($relative, [ref]$actual)) { $mismatches.Add("Missing: $relative"); continue }
        if ($actual.Length -ne [int64]$expected.size_bytes) { $mismatches.Add("Size mismatch: $relative"); continue }
        if ((Get-ExtractedFileSha256 $actual.FullName) -ne $expected.sha256) {
            $mismatches.Add("SHA-256 mismatch: $relative")
        }
    }
    if ($mismatches.Count -eq 0) { $matchedDump = $dump; break }
}
$result = [ordered]@{
    recognized = $null -ne $matchedDump
    source_kind = 'extracted'
    extracted_files_checked = $files.Count
    reason = if ($null -eq $matchedDump) { 'No exact extracted-file catalog match. Modified or incomplete folders are unsupported.' } else { $null }
    mismatches = @($mismatches | Select-Object -First 20)
}
if ($null -ne $matchedDump) {
    $result.dump_id = $matchedDump.id
    $result.status = $matchedDump.status
    $result.title_id = $matchedDump.title_id
    $result.serial = $matchedDump.serial
    # Matching extracted files cannot establish the original ISO's whole-file hash.
    $result.iso_sha256 = $null
    $result.extracted_executables_match = $true
}
if ($Json) { $result | ConvertTo-Json -Depth 6 }
else { [pscustomobject]$result | Format-List }
if ($null -eq $matchedDump) { exit 1 }
