[CmdletBinding()]
param([switch]$JsonEvents)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

. (Join-Path $PSScriptRoot 'release-common.ps1')
$root = Get-PinyonRepoRoot
$config = Get-PinyonReleaseToolchain
$git = Get-PinyonGit
$sdkRoot = Resolve-PinyonRexGlueRoot
$isRepositoryCheckout = Test-Path -LiteralPath (Join-Path $root '.git')

function Invoke-PinyonGitWithRetry {
    param(
        [Parameter(Mandatory)] [string]$Activity,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [scriptblock]$BeforeAttempt
    )

    $maximumAttempts = 3
    for ($attempt = 1; $attempt -le $maximumAttempts; $attempt++) {
        if ($null -ne $BeforeAttempt) { & $BeforeAttempt $attempt }
        & $git @Arguments
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt -lt $maximumAttempts) {
            Write-PinyonEvent tools 35 `
                "$Activity failed (attempt $attempt of $maximumAttempts); retrying." `
                -JsonEvents:$JsonEvents
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
    throw "$Activity failed after $maximumAttempts attempts. Check the build log for the Git error."
}

function Repair-MaterializedLinks {
    param([Parameter(Mandatory)] [string]$RepositoryRoot)
    $mspackRoot = Join-Path $RepositoryRoot 'thirdparty/libmspack'
    if (-not (Test-Path -LiteralPath (Join-Path $mspackRoot '.git'))) { return }
    $entries = @(& $git -C $mspackRoot ls-files -s | Where-Object { $_ -match '^120000 ' })
    foreach ($entry in $entries) {
        if ($entry -notmatch '^120000 [0-9a-f]+ 0\t(.+)$') {
            throw "Unable to parse a libmspack symlink entry: $entry"
        }
        $relative = $Matches[1]
        $targetText = ((& $git -C $mspackRoot show "HEAD:$relative") -join "`n").Trim()
        $linkFile = [IO.Path]::GetFullPath((Join-Path $mspackRoot $relative))
        $targetFile = [IO.Path]::GetFullPath((Join-Path (Split-Path $linkFile -Parent) $targetText))
        $prefix = [IO.Path]::GetFullPath($mspackRoot).TrimEnd('\', '/') +
            [IO.Path]::DirectorySeparatorChar
        if (-not $targetFile.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $targetFile -PathType Leaf)) {
            throw "Invalid libmspack link target for '$relative'."
        }
        $item = Get-Item -LiteralPath $linkFile
        if ($null -eq $item.LinkType) {
            $current = (Get-FileHash -LiteralPath $linkFile -Algorithm SHA256).Hash
            $target = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
            if ($current -ne $target) {
                Copy-Item -LiteralPath $targetFile -Destination $linkFile -Force
            }
        }
    }
}

if ($isRepositoryCheckout) {
    if (-not (Test-Path -LiteralPath (Join-Path $sdkRoot '.git'))) {
        Write-PinyonEvent tools 34 'Initializing the pinned ShiftGlue submodule.' -JsonEvents:$JsonEvents
        Invoke-PinyonGitWithRetry -Activity 'Initializing ShiftGlue' -Arguments @(
            '-c', 'http.version=HTTP/1.1', '-C', $root, 'submodule', 'update',
            '--init', '--recursive', '--jobs', '8', '--', $config.rexglue.submodule_path
        )
    }
    else {
        & $git -C $sdkRoot submodule sync --recursive
        if ($LASTEXITCODE -ne 0) { throw 'Unable to synchronize ShiftGlue dependency URLs.' }
        Invoke-PinyonGitWithRetry -Activity 'Downloading ShiftGlue dependencies' -Arguments @(
            '-c', 'http.version=HTTP/1.1', '-C', $sdkRoot,
            'submodule', 'update', '--init', '--recursive', '--jobs', '8'
        )
    }
}
else {
    $replaceCheckout = $false
    if (Test-Path -LiteralPath $sdkRoot) {
        $head = @(& $git -C $sdkRoot rev-parse HEAD 2>$null | Select-Object -First 1)
        $dirty = @(& $git -C $sdkRoot status --porcelain --ignore-submodules=dirty 2>$null).Count -ne 0
        if ($dirty) {
            throw "The managed ShiftGlue checkout has local changes: $sdkRoot"
        }
        $replaceCheckout = $head.Count -ne 1 -or $head[0] -ne $config.rexglue.revision
    }
    if ($replaceCheckout) {
        $resolved = [IO.Path]::GetFullPath($sdkRoot)
        $allowed = [IO.Path]::GetFullPath((Join-Path $root '.local'))
        if (-not $resolved.StartsWith($allowed.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar,
                [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to replace ShiftGlue outside $allowed"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $sdkRoot)) {
        Write-PinyonEvent tools 34 'Downloading the pinned ShiftGlue source.' -JsonEvents:$JsonEvents
        Invoke-PinyonGitWithRetry -Activity 'Downloading ShiftGlue' -Arguments @(
            '-c', 'core.symlinks=false', '-c', 'http.version=HTTP/1.1',
            'clone', '--no-checkout', '--no-tags', $config.rexglue.repository, $sdkRoot
        ) -BeforeAttempt {
            param($attempt)
            if ($attempt -gt 1 -and (Test-Path -LiteralPath $sdkRoot)) {
                Remove-Item -LiteralPath $sdkRoot -Recurse -Force
            }
        }
        Invoke-PinyonGitWithRetry -Activity 'Fetching the pinned ShiftGlue revision' -Arguments @(
            '-c', 'http.version=HTTP/1.1', '-C', $sdkRoot, 'fetch', '--depth', '1',
            'origin', $config.rexglue.revision
        )
        & $git -C $sdkRoot checkout --detach $config.rexglue.revision
        if ($LASTEXITCODE -ne 0) { throw 'Unable to check out the pinned ShiftGlue revision.' }
    }
    & $git -C $sdkRoot submodule sync --recursive
    if ($LASTEXITCODE -ne 0) { throw 'Unable to synchronize ShiftGlue dependency URLs.' }
    Invoke-PinyonGitWithRetry -Activity 'Downloading ShiftGlue dependencies' -Arguments @(
        '-c', 'http.version=HTTP/1.1', '-C', $sdkRoot,
        'submodule', 'update', '--init', '--recursive', '--jobs', '8'
    )
}

$head = @(& $git -C $sdkRoot rev-parse HEAD 2>$null | Select-Object -First 1)
if ($head.Count -ne 1 -or $head[0] -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Unable to identify the prepared ShiftGlue revision.'
}
if ($head[0] -ne $config.rexglue.revision) {
    Write-PinyonEvent tools 38 "Using developer ShiftGlue revision $($head[0])." -JsonEvents:$JsonEvents
}
Repair-MaterializedLinks -RepositoryRoot $sdkRoot
Write-PinyonEvent tools 39 'ShiftGlue source is ready.' -JsonEvents:$JsonEvents
