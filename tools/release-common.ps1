Set-StrictMode -Version Latest

function Get-PinyonRepoRoot {
    (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-PinyonReleaseToolchain {
    $root = Get-PinyonRepoRoot
    Get-Content -LiteralPath (Join-Path $root 'config/release-toolchain.json') -Raw |
        ConvertFrom-Json
}

function Write-PinyonEvent {
    param(
        [Parameter(Mandatory)] [string]$Stage,
        [Parameter(Mandatory)] [ValidateRange(0, 100)] [int]$Percent,
        [Parameter(Mandatory)] [string]$Message,
        [switch]$JsonEvents
    )
    if ($JsonEvents) {
        $event = [ordered]@{ stage = $Stage; percent = $Percent; message = $Message }
        Write-Output ('::pinyon::' + ($event | ConvertTo-Json -Compress))
    }
    else {
        Write-Host "[$($Stage.ToUpperInvariant())] $Message"
    }
}

function Resolve-PinyonLocalPath {
    param([Parameter(Mandatory)] [string]$RelativePath)
    $root = Get-PinyonRepoRoot
    $full = [IO.Path]::GetFullPath((Join-Path $root $RelativePath))
    $local = [IO.Path]::GetFullPath((Join-Path $root '.local'))
    $prefix = $local.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use a release-work path outside $local"
    }
    $full
}

function Get-PinyonPython {
    $config = Get-PinyonReleaseToolchain
    $pythonRoot = Resolve-PinyonLocalPath -RelativePath $config.python.install_path
    $pythonExe = Join-Path $pythonRoot $config.python.executable
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw 'The local Python runtime is missing. Run tools/provision-toolchain.ps1 first.'
    }
    $pythonExe
}

function Resolve-PinyonRexGlueRoot {
    $root = Get-PinyonRepoRoot
    $config = Get-PinyonReleaseToolchain
    if (Test-Path -LiteralPath (Join-Path $root '.git')) {
        return [IO.Path]::GetFullPath((Join-Path $root $config.rexglue.submodule_path))
    }
    Resolve-PinyonLocalPath -RelativePath $config.rexglue.fallback_path
}

function Invoke-PinyonDownload {
    param(
        [Parameter(Mandatory)] [string]$Uri,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$Sha256
    )
    $parent = Split-Path $Destination -Parent
    [void](New-Item -ItemType Directory -Force -Path $parent)
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
        if ($actual -eq $Sha256) { return }
        Remove-Item -LiteralPath $Destination -Force
    }
    $partial = "$Destination.partial"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    try {
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($null -ne $curl) {
            & $curl.Source --fail --location --retry 3 --output $partial $Uri
            if ($LASTEXITCODE -ne 0) { throw "Download failed: $Uri" }
        }
        else {
            Invoke-WebRequest -Uri $Uri -OutFile $partial -UseBasicParsing
        }
        $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash
        if ($actual -ne $Sha256) {
            throw "Downloaded file failed SHA-256 verification. Expected $Sha256; got $actual."
        }
        Move-Item -LiteralPath $partial -Destination $Destination
    }
    finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}

function Expand-PinyonTarXz {
    param(
        [Parameter(Mandatory)] [string]$Archive,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$XzPath
    )
    $archive = [IO.Path]::GetFullPath($Archive)
    $destination = [IO.Path]::GetFullPath($Destination)
    $xzPath = [IO.Path]::GetFullPath($XzPath)
    $tarArchive = Join-Path (Split-Path $archive -Parent) `
        ([IO.Path]::GetFileNameWithoutExtension($archive))
    if (-not $archive.EndsWith('.tar.xz', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Expected a .tar.xz archive: $archive"
    }
    if (-not (Test-Path -LiteralPath $xzPath -PathType Leaf)) {
        throw "The pinned XZ extractor is missing: $xzPath"
    }
    if (Test-Path -LiteralPath $tarArchive) {
        Remove-Item -LiteralPath $tarArchive -Force
    }
    try {
        & $xzPath --decompress --keep --force -- $archive
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $tarArchive -PathType Leaf)) {
            throw 'Unable to decompress the LLVM toolchain archive.'
        }
        # Windows' own bsdtar by path: a GNU tar earlier in PATH (Git's optional Unix
        # tools, MSYS2) reads "C:\..." as a remote host and fails to extract.
        $tarExe = Join-Path ([Environment]::SystemDirectory) 'tar.exe'
        if (-not (Test-Path -LiteralPath $tarExe -PathType Leaf)) { $tarExe = 'tar.exe' }
        & $tarExe -xf $tarArchive -C $destination
        if ($LASTEXITCODE -ne 0) { throw 'Unable to extract the LLVM toolchain.' }
    }
    finally {
        if (Test-Path -LiteralPath $tarArchive) {
            Remove-Item -LiteralPath $tarArchive -Force
        }
    }
}

function Get-PinyonVisualStudioRoot {
    param([switch]$AllowMissing)
    $config = Get-PinyonReleaseToolchain
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $root = $null
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $root = & $vswhere -latest -products * -requires $config.visual_studio.required_component `
            -version "[$($config.visual_studio.minimum_version),)" -property installationPath | Select-Object -First 1
    }
    if ([string]::IsNullOrWhiteSpace($root) -and -not $AllowMissing) {
        throw "Microsoft C++ Build Tools $($config.visual_studio.minimum_version) or newer were not found. Run tools/provision-toolchain.ps1 to install compatible Visual Studio 2022 Build Tools."
    }
    $root
}

function ConvertTo-PinyonCommandPath {
    param([AllowEmptyString()] [string]$PathValue)

    $entries = @($PathValue -split ';' | ForEach-Object {
        $entry = $_.Trim()
        if ($entry.Length -ge 2 -and $entry.StartsWith('"') -and $entry.EndsWith('"')) {
            $entry = $entry.Substring(1, $entry.Length - 2).Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($entry)) { $entry }
    })
    $entries -join ';'
}

function Get-PinyonCMake {
    param([Parameter(Mandatory)] [string]$VisualStudioRoot)
    $config = Get-PinyonReleaseToolchain
    $candidate = Join-Path (Resolve-PinyonLocalPath $config.cmake.install_path) $config.cmake.executable
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        $candidate = Join-Path $VisualStudioRoot 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw 'CMake is missing. Run tools/provision-toolchain.ps1 first.'
    }
    $versionLines = @(& $candidate --version)
    if ($LASTEXITCODE -ne 0 -or $versionLines.Count -eq 0 -or
        $versionLines[0] -notmatch '^cmake version (\d+\.\d+\.\d+)' -or
        [version]$Matches[1] -lt [version]'3.25.0') {
        throw 'CMake 3.25 or newer is required. Run tools/provision-toolchain.ps1 to install the supported version.'
    }
    $candidate
}

function Format-PinyonCommandLine {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [AllowEmptyCollection()] [string[]]$Arguments = @()
    )
    $parts = foreach ($part in @($FilePath) + @($Arguments)) {
        if ($part -match '[\s"]' -or $part.Length -eq 0) { '"' + ($part -replace '"', '\"') + '"' }
        else { $part }
    }
    $parts -join ' '
}

# Runs a native command, streams its stdout and stderr in arrival order and
# writes the same lines to a UTF-8 log. The caller reads $LASTEXITCODE.
function Invoke-PinyonLoggedCommand {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [AllowEmptyCollection()] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$LogPath,
        [switch]$Append,
        [switch]$Utf8Output
    )
    # Windows PowerShell turns redirected native stderr into ErrorRecord
    # objects. Keep streaming them as plain text and decide success from the
    # process exit code, never from stderr.
    $ErrorActionPreference = 'Continue'
    $parent = Split-Path $LogPath -Parent
    if ($parent) { [void](New-Item -ItemType Directory -Force -Path $parent) }
    $writer = [IO.StreamWriter]::new($LogPath, [bool]$Append, [Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    $savedOutputEncoding = [Console]::OutputEncoding
    try {
        if ($Utf8Output) { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) }
        $writer.WriteLine("> $(Format-PinyonCommandLine -FilePath $FilePath -Arguments $Arguments)")
        if ($null -eq (Get-Command -Name $FilePath -ErrorAction SilentlyContinue)) {
            # With stderr merged, a missing program would only be a log line
            # and $LASTEXITCODE would keep an older value.
            $line = "The program could not be started because it was not found: $FilePath"
            $writer.WriteLine($line)
            $writer.WriteLine('> exit code -1')
            $line
            $global:LASTEXITCODE = -1
            return
        }
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            $line = if ($_ -is [Management.Automation.ErrorRecord]) {
                # ToString() of an empty stderr line is the exception type
                # name, so read the line itself.
                if ($_.TargetObject -is [string]) { $_.TargetObject }
                elseif ($null -ne $_.Exception) { [string]$_.Exception.Message }
                else { $_.ToString() }
            }
            else { [string]$_ }
            $writer.WriteLine($line)
            $line
        }
        $code = $LASTEXITCODE
        $writer.WriteLine("> exit code $code")
    }
    finally {
        $writer.Dispose()
        if ($Utf8Output) { [Console]::OutputEncoding = $savedOutputEncoding }
    }
    $global:LASTEXITCODE = $code
}

# Plain-language causes for failures whose fix is outside the build itself.
function Get-PinyonFailureHint {
    param([AllowEmptyCollection()] [string[]]$Lines = @())
    $text = $Lines -join "`n"
    if ($text -match '(?i)No space left on device|not enough space on the disk|There is not enough space|disk (is )?full|LNK1180|ENOSPC') {
        return 'The drive ran out of free space. Free at least 30 GB on the drive that holds Pinyon Shift, then run setup again.'
    }
    if ($text -match '(?i)out of memory|bad_alloc|not enough memory|Allocation failed|paging file is too small|insufficient system resources|0xC0000017|0xC000012D') {
        return 'The compiler ran out of memory. Close other programs, or let Windows manage the paging file size, then run setup again; it resumes where it stopped.'
    }
    if ($text -match '(?i)contains a virus|potentially unwanted software|Operation did not complete successfully because the file') {
        return 'Antivirus blocked a file the build produced. Allow the Pinyon Shift folder in your antivirus, then run setup again.'
    }
    if ($text -match '(?i)Error copying file|is being used by another process|Access is denied|Permission denied|LNK1104|LNK1168|cannot open (output )?file|failed to write the output file|unable to (open|remove) .* for writing|Could not replace .* beside|open in another program') {
        return 'A file could not be written because another program has it open. Close Pinyon Shift and any tool started from its out\build folder, wait for antivirus scanning to finish (or allow the Pinyon Shift folder in your antivirus), then run setup again.'
    }
    if ($text -match '(?i)PLEASE submit a bug report|frontend command failed due to signal|clang.*crashed|Exception Code: 0x|Stack dump:') {
        return 'The compiler process crashed. This is most often caused by running out of memory or by antivirus stopping the compiler. Close other programs and run setup again; it resumes where it stopped.'
    }
    if ($text -match '(?i)No CMAKE_(C|CXX)_COMPILER could be found|is not a full path to an existing compiler|Could not find any instance of Visual Studio|Unable to initialize the Microsoft x64 build environment|vcvarsall|The C(XX)? compiler identification is unknown') {
        return 'The C++ build tools are missing or incomplete. Restart Windows after installing the Microsoft C++ Build Tools, then run setup again.'
    }
    $null
}

# Finds the lines that explain a failed native command in its complete log:
# the first Ninja FAILED: block, CMake Error blocks, ninja: error lines, or
# error-looking lines near the end. In a parallel build the first failure is
# usually followed by the output of every job that was still running, so the
# tail of the log alone does not identify it.
function Get-PinyonCommandFailureDetail {
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [AllowEmptyString()] [string[]]$Lines,
        [ValidateRange(8, 400)] [int]$MaximumLines = 60
    )
    # Drop the command and exit-code lines Invoke-PinyonLoggedCommand adds.
    $Lines = @($Lines | Where-Object { $_ -notmatch '^> \S' })
    $errorPattern = '(?i)(\berror\b|\bfatal\b|FAILED|LNK\d{4}|undefined (symbol|reference)|cannot |could not |unable to |denied|not found|out of memory|crashed|Stack dump:)'
    $kind = 'none'
    $excerpt = [Collections.Generic.List[string]]::new()
    $failedCount = @($Lines | Where-Object { $_ -match '^FAILED: ' }).Count

    $first = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match '^FAILED: ') { $first = $i; break }
    }
    if ($first -ge 0) {
        $kind = 'ninja'
        $block = [Collections.Generic.List[string]]::new()
        for ($i = $first; $i -lt $Lines.Count; $i++) {
            $line = $Lines[$i]
            if ($i -gt $first -and $line -match '^(FAILED: |\[\d+/\d+\] |ninja: (build stopped|error|warning))') { break }
            if ($i -eq $first + 1 -and $line.Length -gt 600) {
                $line = $line.Substring(0, 600) + ' ...'
            }
            $block.Add($line)
        }
        while ($block.Count -gt 1 -and [string]::IsNullOrWhiteSpace($block[$block.Count - 1])) {
            $block.RemoveAt($block.Count - 1)
        }
        if ($block.Count -le $MaximumLines) {
            $excerpt.AddRange($block)
        }
        else {
            # Keep the FAILED line, the command and the lines around each
            # error instead of a run of warnings.
            $keep = [Collections.Generic.SortedSet[int]]::new()
            [void]$keep.Add(0); if ($block.Count -gt 1) { [void]$keep.Add(1) }
            for ($i = 2; $i -lt $block.Count; $i++) {
                if ($block[$i] -match $errorPattern -and $block[$i] -notmatch '(?i)\bwarning\b') {
                    for ($j = [Math]::Max(2, $i - 1); $j -le [Math]::Min($block.Count - 1, $i + 4); $j++) {
                        [void]$keep.Add($j)
                    }
                }
                if ($keep.Count -ge $MaximumLines) { break }
            }
            if ($keep.Count -le 2) {
                for ($i = 2; $i -lt $MaximumLines; $i++) { [void]$keep.Add($i) }
            }
            $previous = -1
            foreach ($index in $keep) {
                if ($excerpt.Count -ge $MaximumLines) { break }
                if ($previous -ge 0 -and $index -ne $previous + 1) { $excerpt.Add('  ...') }
                $excerpt.Add($block[$index])
                $previous = $index
            }
        }
        if ($failedCount -gt 1) {
            $excerpt.Add("($($failedCount - 1) more command(s) failed; the first failure is shown.)")
        }
    }
    else {
        for ($i = 0; $i -lt $Lines.Count -and $excerpt.Count -lt $MaximumLines; $i++) {
            if ($Lines[$i] -notmatch '^CMake Error') { continue }
            $kind = 'cmake'
            if ($excerpt.Count -gt 0) { $excerpt.Add('') }
            $excerpt.Add($Lines[$i])
            for ($j = $i + 1; $j -lt $Lines.Count -and $excerpt.Count -lt $MaximumLines; $j++) {
                if ($Lines[$j] -match '^(-- |CMake (Error|Warning|Deprecation))') { break }
                $excerpt.Add($Lines[$j])
            }
            $i = $j - 1
        }
        while ($excerpt.Count -gt 0 -and [string]::IsNullOrWhiteSpace($excerpt[$excerpt.Count - 1])) {
            $excerpt.RemoveAt($excerpt.Count - 1)
        }
        $ninjaErrors = @($Lines | Where-Object { $_ -match '^ninja: (error|fatal):' })
        foreach ($line in $ninjaErrors) {
            if ($excerpt.Count -ge $MaximumLines) { break }
            if ($kind -eq 'none') { $kind = 'ninja' }
            $excerpt.Add($line)
        }
    }
    if ($excerpt.Count -eq 0) {
        $meaningful = @($Lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $errors = @($meaningful | Where-Object { $_ -match $errorPattern -and $_ -notmatch '(?i)\bwarning\b' })
        $source = @(if ($errors.Count -gt 0) { $kind = 'errors'; $errors } else { $kind = 'tail'; $meaningful })
        $start = [Math]::Max(0, $source.Count - $MaximumLines)
        for ($i = $start; $i -lt $source.Count; $i++) { $excerpt.Add($source[$i]) }
    }
    [pscustomobject]@{
        Kind = $kind
        Excerpt = [string[]]$excerpt.ToArray()
        Hint = Get-PinyonFailureHint -Lines $excerpt.ToArray()
        FailedCommands = $failedCount
    }
}

function Read-PinyonLogLines {
    param([Parameter(Mandatory)] [string]$LogPath)
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) { return ,([string[]]@()) }
    try { ,([string[]]@(Get-Content -LiteralPath $LogPath -ErrorAction Stop)) }
    catch { ,([string[]]@()) }
}

# An exception describing a failed native step, with the facts
# setup-preview.ps1 records in .local/logs/setup-error.json.
function New-PinyonCommandFailure {
    param(
        [Parameter(Mandatory)] [string]$FailureMessage,
        [Parameter(Mandatory)] [string]$Step,
        [Parameter(Mandatory)] [string]$LogPath,
        [Parameter(Mandatory)] [int]$ExitCode,
        [string]$CommandLine
    )
    $detail = Get-PinyonCommandFailureDetail -Lines (Read-PinyonLogLines -LogPath $LogPath)
    $failure = [Exception]::new("$FailureMessage Exit code: $ExitCode. Build log: $LogPath")
    $failure.Data['step'] = $Step
    $failure.Data['build_log'] = $LogPath
    $failure.Data['exit_code'] = $ExitCode
    if ($CommandLine) { $failure.Data['command'] = $CommandLine }
    $failure.Data['error_kind'] = $detail.Kind
    $failure.Data['error_excerpt'] = $detail.Excerpt
    if ($detail.Hint) { $failure.Data['hint'] = $detail.Hint }
    $failure
}

function Invoke-PinyonBuildCommand {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$LogPath,
        [Parameter(Mandatory)] [string]$FailureMessage,
        [string]$Step
    )
    if (-not $Step) { $Step = [IO.Path]::GetFileNameWithoutExtension($LogPath) }
    Invoke-PinyonLoggedCommand -FilePath $FilePath -Arguments $Arguments -LogPath $LogPath
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw (New-PinyonCommandFailure -FailureMessage $FailureMessage -Step $Step -LogPath $LogPath `
            -ExitCode $code -CommandLine (Format-PinyonCommandLine -FilePath $FilePath -Arguments $Arguments))
    }
}

# A short failure report: what failed, its exit code and log, the error lines
# from the log and a hint. Also written to .local/logs/setup-error.json.
function New-PinyonFailureRecord {
    param(
        [Parameter(Mandatory)] [Management.Automation.ErrorRecord]$ErrorRecord,
        [int]$TailLines = 40
    )
    $exception = $ErrorRecord.Exception
    $data = $exception.Data
    $record = [ordered]@{
        schema_version = 2
        created_utc = [DateTime]::UtcNow.ToString('o')
        message = $exception.Message
        category = [string]$ErrorRecord.CategoryInfo.Category
        script = $ErrorRecord.InvocationInfo.ScriptName
        line = $ErrorRecord.InvocationInfo.ScriptLineNumber
        script_stack = [string]$ErrorRecord.ScriptStackTrace
    }
    foreach ($key in @('step', 'command', 'exit_code', 'build_log', 'error_kind', 'hint')) {
        if ($data.Contains($key) -and $null -ne $data[$key]) { $record[$key] = $data[$key] }
    }
    $logLines = [string[]]@()
    if ($record.Contains('build_log')) { $logLines = Read-PinyonLogLines -LogPath $record.build_log }
    if ($data.Contains('error_excerpt') -and $null -ne $data['error_excerpt']) {
        $record.error_excerpt = [string[]]@($data['error_excerpt'])
    }
    elseif ($logLines.Count -gt 0) {
        $detail = Get-PinyonCommandFailureDetail -Lines $logLines
        $record.error_kind = $detail.Kind
        $record.error_excerpt = $detail.Excerpt
        if ($detail.Hint -and -not $record.Contains('hint')) { $record.hint = $detail.Hint }
    }
    if (-not $record.Contains('hint')) {
        $hintLines = @($exception.Message)
        if ($record.Contains('error_excerpt')) { $hintLines += @($record.error_excerpt) }
        $hint = Get-PinyonFailureHint -Lines $hintLines
        if ($hint) { $record.hint = $hint }
    }
    if ($logLines.Count -gt 0) {
        $start = [Math]::Max(0, $logLines.Count - $TailLines)
        $record.output_tail = [string[]]$logLines[$start..($logLines.Count - 1)]
    }
    $record
}

function Get-PinyonTotalMemoryBytes {
    try {
        [int64](Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop).TotalPhysicalMemory
    }
    catch { [int64]0 }
}

# Parallel compile jobs for this machine. Logical processors alone overcommit
# memory on many-thread, low-memory machines: the largest generated
# translation units peak near 0.9 GB each in clang at -O3, and a link or other
# programs need room too, so budget 1.5 GB per job after 2 GB for Windows.
function Get-PinyonBuildJobCount {
    param(
        [int]$LogicalProcessors = [Environment]::ProcessorCount,
        [int64]$MemoryBytes = -1
    )
    if ($MemoryBytes -lt 0) { $MemoryBytes = Get-PinyonTotalMemoryBytes }
    $jobs = [Math]::Max(2, [Math]::Min(16, $LogicalProcessors - 1))
    if ($MemoryBytes -gt 0) {
        $byMemory = [int][Math]::Floor(($MemoryBytes / 1GB - 2) / 1.5)
        $jobs = [Math]::Max(1, [Math]::Min($jobs, $byMemory))
    }
    $jobs
}

# Machine facts that explain most setup failures (memory, disk, threads).
function Get-PinyonSystemSummary {
    param([Parameter(Mandatory)] [string]$Root)
    $summary = [ordered]@{
        windows_build = [Environment]::OSVersion.Version.Build
        powershell = $PSVersionTable.PSVersion.ToString()
        logical_processors = [Environment]::ProcessorCount
    }
    $memory = Get-PinyonTotalMemoryBytes
    if ($memory -gt 0) { $summary.memory_gb = [Math]::Round($memory / 1GB, 1) }
    try {
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Root)))
        $summary.free_disk_gb = [Math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    }
    catch { }
    $summary
}

function Format-PinyonFailureRecord {
    param(
        [Parameter(Mandatory)] [Collections.IDictionary]$Record,
        [string]$ReportPath = '.local\logs\setup-error.json'
    )
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add('==================== SETUP FAILED ====================')
    $lines.Add("Error: $($Record.message)")
    if ($Record.Contains('step')) { $lines.Add("Failed step: $($Record.step)") }
    if ($Record.Contains('exit_code')) { $lines.Add("Exit code: $($Record.exit_code)") }
    if ($Record.Contains('build_log')) { $lines.Add("Full log: $($Record.build_log)") }
    if ($Record.Contains('error_excerpt') -and @($Record.error_excerpt).Count -gt 0) {
        $lines.Add('First error from the log:')
        foreach ($line in @($Record.error_excerpt)) { $lines.Add("    $line") }
    }
    if ($Record.Contains('hint')) { $lines.Add("What to try: $($Record.hint)") }
    $lines.Add("When reporting this, attach $ReportPath" +
        $(if ($Record.Contains('build_log')) { ' and the full log named above.' } else { '.' }))
    $lines.Add('======================================================')
    [string[]]$lines.ToArray()
}

function Assert-PinyonBuildCapabilities {
    param([Parameter(Mandatory)] [string]$LlvmRoot)
    $compiler = Join-Path $LlvmRoot 'bin/clang++.exe'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
        throw 'The pinned LLVM compiler is missing. Run tools/provision-toolchain.ps1 first.'
    }
    $directory = Join-Path ([IO.Path]::GetTempPath()) ('pinyon-capabilities-' + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $directory)
    $resolvedDirectory = (Resolve-Path -LiteralPath $directory).Path
    $previousPreference = $ErrorActionPreference
    try {
        foreach ($probe in @(
            @{ Name = 'C++23 standard library'; Source = '#include <bit>
static_assert(std::byteswap(0x01020304u) == 0x04030201u);';
               Hint = 'Update the Visual Studio 2022 C++ Build Tools. The selected C++ library must provide std::byteswap.' },
            @{ Name = 'Windows SDK headers'; Source = '#include <windows.h>
#include <d3d12.h>
static_assert(sizeof(D3D12_FEATURE_DATA_D3D12_OPTIONS8) > 0);
constexpr auto feature = D3D12_FEATURE_D3D12_OPTIONS8;';
               Hint = 'Install an updated Windows SDK through the Visual Studio Installer, then rerun setup. The selected d3d12.h must provide D3D12_OPTIONS8.' }
        )) {
            $source = Join-Path $directory 'probe.cpp'
            [IO.File]::WriteAllText($source, $probe.Source)
            $ErrorActionPreference = 'Continue'
            $output = @(& $compiler -std=c++23 -fsyntax-only $source 2>&1 | ForEach-Object { $_.ToString() })
            $exitCode = $LASTEXITCODE
            $ErrorActionPreference = $previousPreference
            if ($exitCode -ne 0) {
                $failure = [Exception]::new("The selected $($probe.Name) failed its build capability check. $($probe.Hint)")
                $failure.Data['step'] = "Check $($probe.Name)"
                $failure.Data['exit_code'] = $exitCode
                $failure.Data['command'] = "`"$compiler`" -std=c++23 -fsyntax-only `"$source`""
                $failure.Data['error_kind'] = 'toolchain-capability'
                $failure.Data['error_excerpt'] = [string[]]$output
                $failure.Data['hint'] = $probe.Hint
                throw $failure
            }
        }
    }
    finally {
        $ErrorActionPreference = $previousPreference
        # Delete only the freshly created, resolved probe directory.
        if ((Resolve-Path -LiteralPath $directory).Path -ne $resolvedDirectory) {
            throw 'The build capability probe directory changed unexpectedly.'
        }
        Remove-Item -LiteralPath $resolvedDirectory -Recurse -Force
    }
}

function Enter-PinyonBuildEnvironment {
    $root = Get-PinyonRepoRoot
    $config = Get-PinyonReleaseToolchain
    $vsRoot = Get-PinyonVisualStudioRoot
    $devCmd = Join-Path $vsRoot 'Common7/Tools/VsDevCmd.bat'
    $inheritedPath = $env:PATH
    $inheritedTemp = $env:TEMP
    $inheritedTmp = $env:TMP
    try {
        # Quoted PATH entries containing parentheses break VsDevCmd's batch parser.
        $env:PATH = ConvertTo-PinyonCommandPath -PathValue $inheritedPath
        # VsDevCmd expands TEMP unquoted inside a parenthesized block even
        # when debug logging is disabled. Portable install paths can break it.
        $buildTemp = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'PinyonShift\build-temp'
        New-Item -ItemType Directory -Path $buildTemp -Force | Out-Null
        $env:TEMP = $buildTemp
        $env:TMP = $buildTemp
        $marker = '::pinyon-environment::'
        # Merged stderr arrives as ErrorRecords; under 'Stop' the first one
        # would end the function before the exit code is known.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = @(& $env:ComSpec /d /s /c "`"$devCmd`" -arch=x64 -host_arch=x64 && echo $marker&& set" 2>&1 |
            ForEach-Object { $_.ToString() })
        $devCmdExit = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
    }
    finally {
        $env:PATH = $inheritedPath
        $env:TEMP = $inheritedTemp
        $env:TMP = $inheritedTmp
    }
    $markerIndex = -1
    for ($i = 0; $i -lt $output.Count; $i++) {
        if ($output[$i].Trim() -eq $marker) { $markerIndex = $i; break }
    }
    if ($devCmdExit -ne 0 -or $markerIndex -lt 0) {
        # VsDevCmd prints its own [ERROR:...] lines; keep them in the report.
        $devCmdOutput = @($output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 20)
        $failure = [Exception]::new('Unable to initialize the Microsoft x64 build environment. Restart Windows after installing the Microsoft C++ Build Tools, then run setup again. ' +
            "VsDevCmd: $devCmd")
        $failure.Data['step'] = 'Initialize the Microsoft x64 build environment'
        $failure.Data['exit_code'] = $devCmdExit
        $failure.Data['command'] = "`"$devCmd`" -arch=x64 -host_arch=x64"
        $failure.Data['error_excerpt'] = [string[]]$devCmdOutput
        throw $failure
    }
    $lines = if ($markerIndex + 1 -lt $output.Count) { $output[($markerIndex + 1)..($output.Count - 1)] } else { @() }
    foreach ($line in $lines) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) {
            $name = $line.Substring(0, $separator)
            if ($name -in @('TEMP', 'TMP')) { continue }
            [Environment]::SetEnvironmentVariable($name,
                $line.Substring($separator + 1), 'Process')
        }
    }
    $llvm = [IO.Path]::GetFullPath((Join-Path $root $config.llvm.install_path))
    $env:PATH = "$(Join-Path $llvm 'bin');$env:PATH"
    Assert-PinyonBuildCapabilities -LlvmRoot $llvm
    [pscustomobject]@{
        VisualStudioRoot = $vsRoot
        CMake = Get-PinyonCMake -VisualStudioRoot $vsRoot
        Ninja = Join-Path $vsRoot 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
        LlvmRoot = $llvm
    }
}

# A CMake build tree records its absolute location, and CMake refuses to configure one
# that was moved (a portable install taken to another drive or PC). Such a tree is
# configured afresh; the build then recompiles what the new paths invalidate. Returns
# whether the cache was removed.
function Reset-PinyonRelocatedCMakeCache {
    param([Parameter(Mandatory)] [string]$BuildDirectory)
    $cache = Join-Path $BuildDirectory 'CMakeCache.txt'
    if (-not (Test-Path -LiteralPath $cache -PathType Leaf)) { return $false }
    $line = Select-String -LiteralPath $cache -Pattern '^CMAKE_CACHEFILE_DIR:INTERNAL=(.+)$' |
        Select-Object -First 1
    if ($null -eq $line) { return $false }
    $recorded = [IO.Path]::GetFullPath($line.Matches[0].Groups[1].Value.Trim()).TrimEnd('\', '/')
    $current = [IO.Path]::GetFullPath($BuildDirectory).TrimEnd('\', '/')
    if ([string]::Equals($recorded, $current, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    Remove-Item -LiteralPath $cache -Force
    $cmakeFiles = Join-Path $BuildDirectory 'CMakeFiles'
    if (Test-Path -LiteralPath $cmakeFiles) { Remove-Item -LiteralPath $cmakeFiles -Recurse -Force }
    return $true
}

function Get-PinyonGit {
    $root = Get-PinyonRepoRoot
    $config = Get-PinyonReleaseToolchain
    $candidate = Join-Path (Join-Path $root $config.git.install_path) $config.git.executable
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw 'Git is not available. Run provision-toolchain.ps1 first.'
    }
    $candidate
}

function Get-PinyonSourceProvenance {
    param(
        [Parameter(Mandatory)] [string]$Root,
        [Parameter(Mandatory)] [string]$Git
    )

    $sourceCommit = $null
    $sourceDirty = $false
    # Launcher payloads are source archives, not Git working trees. Avoid
    # invoking Git there because Windows PowerShell promotes native stderr to a
    # terminating error before the packaged provenance fallback can run.
    if (Test-Path -LiteralPath (Join-Path $Root '.git')) {
        $gitCommit = @(& $Git -C $Root rev-parse HEAD 2>$null | Select-Object -First 1)
        if ($gitCommit.Count -eq 1 -and $gitCommit[0] -match '^[0-9a-fA-F]{40}$') {
            $sourceCommit = $gitCommit[0].ToLowerInvariant()
            $sourceDirty = @(& $Git -C $Root status --porcelain).Count -ne 0
        }
    }

    if (-not $sourceCommit) {
        $sourceProvenancePath = Join-Path $Root 'config/source-provenance.json'
        if (Test-Path -LiteralPath $sourceProvenancePath -PathType Leaf) {
            $sourceProvenance = Get-Content -LiteralPath $sourceProvenancePath -Raw |
                ConvertFrom-Json
            if ($sourceProvenance.commit -match '^[0-9a-fA-F]{40}$') {
                $sourceCommit = $sourceProvenance.commit.ToLowerInvariant()
                $sourceDirty = [bool]$sourceProvenance.dirty
            }
        }
    }

    if (-not $sourceCommit) {
        throw 'Build provenance requires an exact Pinyon Shift commit.'
    }
    [pscustomobject]@{ Commit = $sourceCommit; Dirty = $sourceDirty }
}
