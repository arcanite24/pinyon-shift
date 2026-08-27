[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateNotNullOrEmpty()] [string]$LogPath,
    [string]$AllowlistPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $AllowlistPath) {
    $AllowlistPath = Join-Path $root 'config/rexglue/accepted-codegen-warnings.json'
}
$resolvedLog = (Resolve-Path -LiteralPath $LogPath).Path
$resolvedAllowlist = (Resolve-Path -LiteralPath $AllowlistPath).Path
$config = Get-Content -LiteralPath $resolvedAllowlist -Raw | ConvertFrom-Json
if ($config.schema_version -ne 1 -or $null -eq $config.warnings) {
    throw 'Unsupported warning allowlist schema.'
}

$matches = [ordered]@{}
foreach ($rule in @($config.warnings)) {
    if ([string]::IsNullOrWhiteSpace($rule.id) -or
        [string]::IsNullOrWhiteSpace($rule.pattern) -or
        [string]::IsNullOrWhiteSpace($rule.reason)) {
        throw 'Every accepted warning needs id, pattern, and reason.'
    }
    $matches[$rule.id] = 0
}

$warningPrefix = '\[warning\]\s+\[codegen\](?:\s+\[t\d+\])?\s+(?<message>.+)$'
$unknown = [Collections.Generic.List[string]]::new()
$warningCount = 0
foreach ($line in [IO.File]::ReadLines($resolvedLog)) {
    $marker = [regex]::Match($line, $warningPrefix, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $marker.Success) { continue }
    $warningCount++
    $message = $marker.Groups['message'].Value.Trim()
    $matching = @($config.warnings | Where-Object {
        [regex]::IsMatch($message, $_.pattern) -and
        [regex]::Match($message, $_.pattern).Value -eq $message
    })
    if ($matching.Count -eq 1) {
        $matches[$matching[0].id]++
    } elseif ($matching.Count -eq 0) {
        $unknown.Add($message)
    } else {
        $unknown.Add("ambiguous allowlist match: $message")
    }
}

$missing = @($matches.Keys | Where-Object { $matches[$_] -eq 0 } | Sort-Object)
if ($unknown.Count -gt 0 -or $missing.Count -gt 0) {
    $details = [Collections.Generic.List[string]]::new()
    if ($unknown.Count -gt 0) {
        $details.Add('unrecognized warnings: ' + (($unknown | Sort-Object -Unique) -join ' | '))
    }
    if ($missing.Count -gt 0) {
        $details.Add('expected warnings not observed: ' + ($missing -join ', '))
    }
    throw ($details -join '; ')
}

[ordered]@{
    schema = 'pinyon-shift.codegen-warning-verification.v1'
    log = [IO.Path]::GetFileName($resolvedLog)
    warning_count = $warningCount
    accepted = $matches
} | ConvertTo-Json -Depth 4
