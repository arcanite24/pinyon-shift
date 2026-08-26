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
$sdkRoot = Resolve-PinyonLocalPath -RelativePath $config.rexglue.path
$markerPath = Join-Path $sdkRoot '.pinyon-patches.json'
$patches = @(Get-ChildItem -LiteralPath (Join-Path $root $config.rexglue.patch_directory) `
    -Filter '*.patch' -File | Sort-Object Name)
$patchRecords = @($patches | ForEach-Object {
    [ordered]@{ name = $_.Name; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
})
$expectedMarker = [ordered]@{
    schema_version = 1
    tag = $config.rexglue.tag
    base_commit = $config.rexglue.base_commit
    patches = $patchRecords
}
$expectedJson = $expectedMarker | ConvertTo-Json -Depth 5

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

if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
    $actualJson = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 5
    if ($actualJson -eq $expectedJson) {
        Repair-MaterializedLinks -RepositoryRoot $sdkRoot
        Write-PinyonEvent tools 36 'ReXGlue source and project patches are already prepared.' -JsonEvents:$JsonEvents
        return
    }
}

if (Test-Path -LiteralPath $sdkRoot) {
    $resolved = [IO.Path]::GetFullPath($sdkRoot)
    $allowed = [IO.Path]::GetFullPath((Join-Path $root '.local'))
    if (-not $resolved.StartsWith($allowed.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace ReXGlue outside $allowed"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

Write-PinyonEvent tools 34 'Downloading the pinned ReXGlue source.' -JsonEvents:$JsonEvents
& $git -c core.symlinks=false clone --recursive --no-tags $config.rexglue.repository $sdkRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to download ReXGlue and its dependencies.' }
& $git -C $sdkRoot fetch --no-tags origin `
    "refs/tags/$($config.rexglue.tag):refs/tags/$($config.rexglue.tag)"
if ($LASTEXITCODE -ne 0) { throw 'Unable to fetch the pinned ReXGlue release tag.' }
$tagCommit = (& $git -C $sdkRoot rev-list -n 1 $config.rexglue.tag).Trim()
if ($LASTEXITCODE -ne 0 -or $tagCommit -ne $config.rexglue.base_commit) {
    throw "ReXGlue tag $($config.rexglue.tag) does not resolve to the pinned commit."
}
& $git -C $sdkRoot checkout --detach $config.rexglue.base_commit
if ($LASTEXITCODE -ne 0) { throw 'Unable to check out the pinned ReXGlue revision.' }
& $git -C $sdkRoot submodule update --init --recursive --jobs 8
if ($LASTEXITCODE -ne 0) { throw 'Unable to prepare ReXGlue dependencies.' }

Write-PinyonEvent tools 37 'Applying the Pinyon Shift compatibility patches.' -JsonEvents:$JsonEvents
foreach ($patch in $patches) {
    & $git -C $sdkRoot apply --check --whitespace=nowarn $patch.FullName
    if ($LASTEXITCODE -ne 0) { throw "Compatibility patch cannot be applied: $($patch.Name)" }
    & $git -C $sdkRoot apply --whitespace=nowarn $patch.FullName
    if ($LASTEXITCODE -ne 0) { throw "Compatibility patch failed: $($patch.Name)" }
}
[IO.File]::WriteAllText($markerPath, $expectedJson + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false))
Repair-MaterializedLinks -RepositoryRoot $sdkRoot
Write-PinyonEvent tools 39 'ReXGlue source is ready.' -JsonEvents:$JsonEvents
