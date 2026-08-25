[CmdletBinding()]
param(
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$policyPath = Join-Path $repoRoot 'config/repository-policy.json'
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json

Push-Location $repoRoot
try {
    $candidateFiles = @(git -c core.quotePath=false ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw 'git ls-files failed.'
    }
}
finally {
    Pop-Location
}

$violations = [System.Collections.Generic.List[object]]::new()
$forbiddenExtensions = @($policy.forbidden_extensions | ForEach-Object { $_.ToLowerInvariant() })
$forbiddenSegments = @($policy.forbidden_path_segments | ForEach-Object { $_.ToLowerInvariant() })
$allowedLargeFiles = @($policy.allowed_large_files | ForEach-Object { $_.Replace('\', '/').ToLowerInvariant() })

foreach ($relativePath in $candidateFiles) {
    $normalized = $relativePath.Replace('\', '/')
    $normalizedLower = $normalized.ToLowerInvariant()
    $fullPath = Join-Path $repoRoot $relativePath

    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }

    $extension = [IO.Path]::GetExtension($relativePath).ToLowerInvariant()
    if ($extension -in $forbiddenExtensions) {
        $violations.Add([pscustomobject]@{
            path = $normalized
            rule = 'forbidden_extension'
            detail = $extension
        })
    }

    $segments = @($normalizedLower.Split('/'))
    $blockedSegment = $segments | Where-Object { $_ -in $forbiddenSegments } | Select-Object -First 1
    if ($null -ne $blockedSegment) {
        $violations.Add([pscustomobject]@{
            path = $normalized
            rule = 'forbidden_path_segment'
            detail = $blockedSegment
        })
    }

    foreach ($pattern in $policy.forbidden_file_name_patterns) {
        if ([IO.Path]::GetFileName($relativePath) -match $pattern) {
            $violations.Add([pscustomobject]@{
                path = $normalized
                rule = 'forbidden_file_name'
                detail = $pattern
            })
        }
    }

    $fileInfo = Get-Item -LiteralPath $fullPath
    if ($fileInfo.Length -gt [int64]$policy.max_public_file_bytes -and
        $normalizedLower -notin $allowedLargeFiles) {
        $violations.Add([pscustomobject]@{
            path = $normalized
            rule = 'unreviewed_large_file'
            detail = "$($fileInfo.Length) bytes"
        })
    }

    if ($fileInfo.Length -ge 4) {
        $stream = [IO.File]::OpenRead($fullPath)
        try {
            $buffer = [byte[]]::new(4)
            [void]$stream.Read($buffer, 0, 4)
            $magic4 = [Text.Encoding]::ASCII.GetString($buffer)
            $magic2 = $magic4.Substring(0, 2)
            foreach ($magic in $policy.forbidden_magic_ascii) {
                if ($magic4 -eq $magic -or $magic2 -eq $magic) {
                    $violations.Add([pscustomobject]@{
                        path = $normalized
                        rule = 'forbidden_file_magic'
                        detail = $magic
                    })
                }
            }
        }
        finally {
            $stream.Dispose()
        }
    }
}

$result = [pscustomobject]@{
    schema_version = 1
    checked_files = $candidateFiles.Count
    violation_count = $violations.Count
    violations = @($violations)
}

if ($Json) {
    $result | ConvertTo-Json -Depth 5
}
else {
    if ($violations.Count -eq 0) {
        Write-Host "Repository boundary check passed ($($candidateFiles.Count) candidate files)."
    }
    else {
        $violations | Format-Table path, rule, detail -AutoSize
    }
}

if ($violations.Count -ne 0) {
    exit 1
}
