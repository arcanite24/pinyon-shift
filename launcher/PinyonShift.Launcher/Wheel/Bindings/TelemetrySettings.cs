namespace PinyonShift.Launcher.Wheel.Bindings;

/// <summary>Telemetry out for SimHub, dashboards and shakers: the same keys as F6 > GAMEPLAY >
/// TELEMETRY OUT and the telemetry_udp_* settings.</summary>
public sealed class TelemetrySettings
{
    public bool Enabled { get; set; }
    public bool Horizon { get; set; }  // Forza Horizon 4/5 layout, or Forza Motorsport 7 (the game's default)
    public bool MovingOnly { get; set; }
    // The game's telemetry_udp_target default.
    public const string DefaultPort = ":5300";
    public const string DefaultTarget = "127.0.0.1" + DefaultPort;

    public string Target { get; set; } = DefaultTarget;

    public void Load(IReadOnlyDictionary<string, string> config)
    {
        bool Bool(string key) => config.TryGetValue(key, out var v) && v.Equals("true", StringComparison.OrdinalIgnoreCase);
        Enabled = Bool("telemetry_udp");
        MovingOnly = Bool("telemetry_udp_moving_only");
        Horizon = config.TryGetValue("telemetry_udp_format", out var f) && f.Equals("horizon", StringComparison.OrdinalIgnoreCase);
        Target = config.TryGetValue("telemetry_udp_target", out var t) && t.Contains(':') ? t : DefaultTarget;
    }

    public List<(string Key, string Value)> ConfigLines() =>
    [
        ("telemetry_udp", Enabled ? "true" : "false"),
        ("telemetry_udp_format", Horizon ? "\"horizon\"" : "\"fm7\""),
        ("telemetry_udp_moving_only", MovingOnly ? "true" : "false"),
        ("telemetry_udp_target", BindingSet.TomlString(Target)),
    ];

    public string Summary() => Enabled ? (Horizon ? "On · Horizon" : "On · FM7") : "Off";
}
