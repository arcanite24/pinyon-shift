using System.Globalization;

namespace PinyonWheelSetup.Bindings;

/// <summary>The game's display settings this app sets: window size, full screen, the ultrawide
/// wider view, resolution scale and field of view. The same keys F6 > SETTINGS writes.</summary>
public sealed class DisplaySettings
{
    public sealed record Size(int Width, int Height, string Label)
    {
        public override string ToString() => Label;
        /// <summary>Wider than 16:9, where the wider view is what fills the window.</summary>
        public bool Wide => Width > 0 && Width * 9L > Height * 16L;
    }

    public static readonly Size[] Sizes =
    [
        new(0, 0, "Game default"),
        new(1280, 720, "1280 × 720 (16:9)"),
        new(1920, 1080, "1920 × 1080 (16:9)"),
        new(2560, 1440, "2560 × 1440 (16:9)"),
        new(3840, 2160, "3840 × 2160 (16:9)"),
        new(3440, 1440, "3440 × 1440 (21:9)"),
        new(5120, 1440, "5120 × 1440 (32:9)"),
        new(10240, 1440, "10240 × 1440 (64:9)"),
    ];

    public static readonly double[] FovScales = [0.9, 1.0, 1.1, 1.2, 1.3];

    public int Width { get; set; }
    public int Height { get; set; }
    public bool Fullscreen { get; set; } = true;
    public bool WiderView { get; set; }
    public int Scale { get; set; } = 1;  // 1x to 4x of the console's 1280 x 720
    public double Fov { get; set; } = 1.0;

    public Size CurrentSize => Sizes.FirstOrDefault(s => s.Width == Width && s.Height == Height)
                               ?? new Size(Width, Height, $"{Width} × {Height}");

    public void Load(IReadOnlyDictionary<string, string> config)
    {
        int Int(string key, int fallback) =>
            config.TryGetValue(key, out var v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int n) ? n : fallback;
        bool Bool(string key, bool fallback) =>
            config.TryGetValue(key, out var v) ? v.Equals("true", StringComparison.OrdinalIgnoreCase) : fallback;

        Width = Math.Max(0, Int("window_width", 0));
        Height = Math.Max(0, Int("window_height", 0));
        if (Width == 0 || Height == 0) Width = Height = 0;
        Fullscreen = Bool("fullscreen", true);
        WiderView = Bool("pinyon_shift_hor_plus", false);
        Scale = Math.Clamp(Int("draw_resolution_scale_x", 1), 1, 4);
        Fov = config.TryGetValue("pinyon_shift_fov_scale", out var fov) &&
              double.TryParse(fov, NumberStyles.Float, CultureInfo.InvariantCulture, out double f)
            ? Math.Clamp(f, 0.5, 2.0) : 1.0;
    }

    public List<(string Key, string Value)> ConfigLines()
    {
        string I(int value) => value.ToString(CultureInfo.InvariantCulture);
        return
        [
            ("window_width", I(Width)),
            ("window_height", I(Height)),
            ("fullscreen", Fullscreen ? "true" : "false"),
            ("pinyon_shift_hor_plus", WiderView ? "true" : "false"),
            // As F6 does: the wider view stretches the widened frame over the window, and off
            // goes back to letterboxing the game's 16:9 image.
            ("present_letterbox", WiderView ? "false" : "true"),
            ("present_allow_overscan_cutoff", "false"),
            ("draw_resolution_scale_x", I(Scale)),
            ("draw_resolution_scale_y", I(Scale)),
            ("pinyon_shift_fov_scale", Fov.ToString("0.0", CultureInfo.InvariantCulture)),
        ];
    }

    /// <summary>The card header's one line.</summary>
    public string Summary()
    {
        string size = Fullscreen ? "Full screen" : Width == 0 ? "Default window" : $"{Width}×{Height}";
        return size + (WiderView ? " · wider view" : "") + $" · {Scale}×";
    }
}
