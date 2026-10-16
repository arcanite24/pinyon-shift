# Pulls the game's wheel and force feedback functions out of the locally generated code, so the
# racing wheel work can match how FH1 drives an Xbox 360 FFB wheel (the XInputdFF* kernel calls).
#   powershell -ExecutionPolicy Bypass -File extract-wheel-code.ps1 [-Install "D:\Games\Pinyon Shift"]
# Writes fh1-wheel-guest-code.txt beside this script. It holds only these functions, generated on
# your PC from your own disc; keep it private (don't post it publicly).
param([string]$Install)
# The launcher's install folder (its choice in install-root.txt, else its default) and the newest
# source version in it.
if (-not $Install) {
    $pref = Join-Path $env:LOCALAPPDATA 'PinyonShift\install-root.txt'
    $Install = if (Test-Path $pref) { (Get-Content $pref -Raw).Trim() } else { Join-Path $env:LOCALAPPDATA 'PinyonShift' }
}
$source = Get-ChildItem (Join-Path $Install 'source') -Directory -ErrorAction SilentlyContinue |
    Sort-Object { try { [version]$_.Name } catch { [version]'0.0' } } | Select-Object -Last 1 -ExpandProperty FullName
if (-not $source) { throw "No Pinyon Shift source under $Install (pass -Install with your install folder)" }

$gen = Join-Path $source '.local\generated\default'
if (-not (Test-Path $gen)) { throw "Generated code not found: $gen" }
$out = Join-Path $PSScriptRoot 'fh1-wheel-guest-code.txt'

# The input module (0x82BF8000-0x82BFFFFF), the XInput wrappers near 0x830EB900 and the wheel
# FFB module around 0x8310C000-0x8310DFFF, plus any function that calls an XInputdFF export.
$ranges = '(?i)^DEFINE_REX_FUNC\((?:sub_)?(82BF[89A-F][0-9A-F]{3}|830EB[89A][0-9A-F]{2}|8310[B-E][0-9A-F]{3})\)'
$sb = New-Object System.Text.StringBuilder
$functions = 0
foreach ($file in Get-ChildItem $gen -Filter *.cpp) {
    $current = $null
    $keep = $false
    foreach ($line in [IO.File]::ReadLines($file.FullName)) {
        if ($line.StartsWith('DEFINE_REX_FUNC(')) {
            if ($current -and ($keep -or $current.ToString().Contains('XInputdFF'))) {
                [void]$sb.AppendLine("// ==== $($file.Name)"); [void]$sb.Append($current.ToString()); $functions++
            }
            $current = New-Object System.Text.StringBuilder
            $keep = $line -match $ranges
        }
        if ($current) { [void]$current.AppendLine($line) }
    }
    if ($current -and ($keep -or $current.ToString().Contains('XInputdFF'))) {
        [void]$sb.AppendLine("// ==== $($file.Name)"); [void]$sb.Append($current.ToString()); $functions++
    }
}
[IO.File]::WriteAllText($out, $sb.ToString())
$mb = (Get-Item $out).Length / 1MB
Write-Host ("{0} functions, {1:N1} MB -> {2}" -f $functions, $mb, $out)
