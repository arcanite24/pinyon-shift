# Generates src/PinyonWheelSetup/Assets/App.ico (multi-size, PNG-compressed entries).
# Same rounded square and blue gradient as MCAL, with a steering wheel glyph.
# Run with Windows PowerShell 5.1: powershell -File tools\make-icon.ps1
Add-Type -AssemblyName System.Drawing

$out = Join-Path $PSScriptRoot '..\src\PinyonWheelSetup\Assets\App.ico'
$sizes = 16, 24, 32, 48, 64, 128, 256
$pngs = @()

foreach ($s in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap $s, $s
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)

    # rounded square background
    $r = [single]($s * 0.22)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $w = [single]($s - 1)
    $path.AddArc(0, 0, $r * 2, $r * 2, 180, 90)
    $path.AddArc($w - $r * 2, 0, $r * 2, $r * 2, 270, 90)
    $path.AddArc($w - $r * 2, $w - $r * 2, $r * 2, $r * 2, 0, 90)
    $path.AddArc(0, $w - $r * 2, $r * 2, $r * 2, 90, 90)
    $path.CloseFigure()
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush (New-Object System.Drawing.Point 0, 0), (New-Object System.Drawing.Point $s, $s), ([System.Drawing.Color]::FromArgb(255, 0, 95, 184)), ([System.Drawing.Color]::FromArgb(255, 76, 194, 255))
    $g.FillPath($brush, $path)

    # steering wheel: rim, hub and three spokes
    $c = $s / 2.0
    $rim = $s * 0.31
    $stroke = [single][Math]::Max(1.5, $s * 0.085)
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), $stroke
    $g.DrawEllipse($pen, [single]($c - $rim), [single]($c - $rim), [single]($rim * 2), [single]($rim * 2))
    $spoke = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), ([single][Math]::Max(1.2, $s * 0.07))
    $g.DrawLine($spoke, [single]($c - $rim), [single]$c, [single]($c + $rim), [single]$c)
    $g.DrawLine($spoke, [single]$c, [single]$c, [single]$c, [single]($c + $rim))
    $hub = $s * 0.09
    $white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $g.FillEllipse($white, [single]($c - $hub), [single]($c - $hub), [single]($hub * 2), [single]($hub * 2))
    $g.Dispose()

    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngs += , $ms.ToArray()
    $bmp.Dispose()
}

$fs = [System.IO.File]::Create($out)
$bw = New-Object System.IO.BinaryWriter $fs
$bw.Write([uint16]0); $bw.Write([uint16]1); $bw.Write([uint16]$sizes.Count)
$offset = 6 + 16 * $sizes.Count
for ($i = 0; $i -lt $sizes.Count; $i++) {
    $s = $sizes[$i]
    $dim = if ($s -ge 256) { 0 } else { $s }
    $bw.Write([byte]$dim); $bw.Write([byte]$dim); $bw.Write([byte]0); $bw.Write([byte]0)
    $bw.Write([uint16]1); $bw.Write([uint16]32)
    $bw.Write([uint32]$pngs[$i].Length); $bw.Write([uint32]$offset)
    $offset += $pngs[$i].Length
}
foreach ($p in $pngs) { $bw.Write($p) }
$bw.Close()
Write-Host "Wrote $out"
