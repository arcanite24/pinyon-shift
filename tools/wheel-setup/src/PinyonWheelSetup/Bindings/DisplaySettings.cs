using System.Globalization;
using System.Runtime.InteropServices;

namespace PinyonWheelSetup.Bindings;

/// <summary>The game's display settings this app sets: full screen, the ultrawide wider view,
/// resolution scale and field of view, with the same keys F6 > SETTINGS writes.
///
/// With the wider view on, the game draws the window's wider view into its 16:9 frame. Scaling
/// that frame more across than down (draw_resolution_scale_x over _y, which the renderer allows
/// up to 7 each) renders it at the display's own width instead of stretching it, so a 32:9
/// display gets 4x across and 2x down: 5120 x 1440 real pixels.</summary>
public sealed class DisplaySettings
{
    public const int MaxScaleAcross = 7;
    public static readonly double[] FovScales = [0.9, 1.0, 1.1, 1.2, 1.3];

    public bool Fullscreen { get; set; } = true;
    public bool WiderView { get; set; }
    public int Scale { get; set; } = 1;  // down: 1x to 4x of the console's 720 lines
    public double Fov { get; set; } = 1.0;

    /// <summary>The primary display's size in pixels (a Surround or Eyefinity group counts as one).</summary>
    public (int Width, int Height) DisplaySize { get; set; } = PrimaryDisplay();

    /// <summary>Across: the display's aspect over 16:9 times the scale down, while the wider view is on.</summary>
    public int ScaleAcross
    {
        get
        {
            var (w, h) = DisplaySize;
            if (!WiderView || w <= 0 || h <= 0) return Scale;
            double wide = (w / (double)h) / (16.0 / 9.0);
            return Math.Clamp((int)Math.Round(Scale * Math.Max(1.0, wide)), Scale, MaxScaleAcross);
        }
    }

    public void Load(IReadOnlyDictionary<string, string> config)
    {
        int Int(string key, int fallback) =>
            config.TryGetValue(key, out var v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int n) ? n : fallback;
        bool Bool(string key, bool fallback) =>
            config.TryGetValue(key, out var v) ? v.Equals("true", StringComparison.OrdinalIgnoreCase) : fallback;

        Fullscreen = Bool("fullscreen", true);
        WiderView = Bool("pinyon_shift_hor_plus", false);
        Scale = Math.Clamp(Int("draw_resolution_scale_y", Int("draw_resolution_scale_x", 1)), 1, 4);
        Fov = config.TryGetValue("pinyon_shift_fov_scale", out var fov) &&
              double.TryParse(fov, NumberStyles.Float, CultureInfo.InvariantCulture, out double f)
            ? Math.Clamp(f, 0.5, 2.0) : 1.0;
    }

    public List<(string Key, string Value)> ConfigLines()
    {
        string I(int value) => value.ToString(CultureInfo.InvariantCulture);
        return
        [
            ("fullscreen", Fullscreen ? "true" : "false"),
            ("pinyon_shift_hor_plus", WiderView ? "true" : "false"),
            // As F6 does: the wider view fills the window, and off goes back to letterboxing the
            // game's 16:9 image.
            ("present_letterbox", WiderView ? "false" : "true"),
            ("present_allow_overscan_cutoff", "false"),
            ("draw_resolution_scale_x", I(ScaleAcross)),
            ("draw_resolution_scale_y", I(Scale)),
            ("pinyon_shift_fov_scale", Fov.ToString("0.0", CultureInfo.InvariantCulture)),
        ];
    }

    /// <summary>What the game will render, for the card.</summary>
    public string RenderText()
    {
        int across = ScaleAcross;
        string size = $"{1280 * across} × {720 * Scale}";
        var (w, h) = DisplaySize;
        if (!WiderView)
            return $"Renders {size}, 16:9.";
        bool capped = Scale * (w / (double)h) / (16.0 / 9.0) > MaxScaleAcross + 0.5;
        string note = capped ? $" ({MaxScaleAcross}× across is the most the renderer allows, so the rest is stretched)" : "";
        return $"Renders {size} ({across}× across, {Scale}× down) for your {w} × {h} display{note}." +
               (across != Scale ? " Rendering wider than 16:9 uses the game's general renderer, which is slower than its 16:9 path." : "");
    }

    /// <summary>The card header's one line.</summary>
    public string Summary() =>
        (Fullscreen ? "Full screen" : "Window") + (WiderView ? " · wide" : "") + $" · {ScaleAcross}×{Scale}";

    [DllImport("user32.dll")] private static extern IntPtr GetDC(IntPtr window);
    [DllImport("user32.dll")] private static extern int ReleaseDC(IntPtr window, IntPtr dc);
    [DllImport("gdi32.dll")] private static extern int GetDeviceCaps(IntPtr dc, int index);

    private static (int, int) PrimaryDisplay()
    {
        const int DesktopVertRes = 117, DesktopHorzRes = 118;  // physical pixels, whatever the DPI
        IntPtr dc = GetDC(IntPtr.Zero);
        try { return (GetDeviceCaps(dc, DesktopHorzRes), GetDeviceCaps(dc, DesktopVertRes)); }
        finally { ReleaseDC(IntPtr.Zero, dc); }
    }
}
