using System.ComponentModel;
using System.Globalization;
using PinyonShift.Launcher.Wheel.Input;

namespace PinyonShift.Launcher.Wheel.Bindings;

public enum BindKind { Steering, Pedal, Button }
public enum InputType { Axis, Button, Hat }

/// <summary>Which device an input is on: what the game's device match needs.</summary>
public sealed record DeviceKey(string Name, string Path, ushort Vendor, ushort Product)
{
    public static DeviceKey Of(Device d) => new(d.Name, d.Path, d.Vendor, d.Product);

    public bool Is(Device d) =>
        Path.Length > 0 && d.Path.Length > 0
            ? string.Equals(Path, d.Path, StringComparison.OrdinalIgnoreCase)
            : d.Vendor == Vendor && d.Product == Product && d.Name == Name;
}

/// <summary>One physical input: an axis, button or hat direction on one device.</summary>
public sealed class InputRef
{
    public DeviceKey? Device { get; init; }
    /// <summary>The device text from the config when that device is not connected; written back as-is.</summary>
    public string? Unresolved { get; init; }
    public InputType Type { get; init; }
    public int Index { get; init; }
    public byte HatMask { get; init; }
    /// <summary>Axis travel reversed: steering invert, a pedal resting at the top (−), or a lever pressed downwards.</summary>
    public bool Inverted { get; set; }

    public bool SameInput(InputRef other) =>
        Type == other.Type && Index == other.Index && HatMask == other.HatMask &&
        Device != null && other.Device != null && Device == other.Device;

    public string Describe() => Type switch
    {
        InputType.Axis => $"axis {Index}",
        InputType.Button => $"button {Index}",
        _ => $"hat {Index} {WheelMath.HatName(HatMask)}",
    };
}

public sealed class BindingItem : INotifyPropertyChanged
{
    public required string Key { get; init; }       // the game's control name (A, LB, ...) or STEER/THROTTLE/...
    public required string Label { get; init; }
    public required string Prompt { get; init; }
    public BindKind Kind { get; init; }
    public bool IsAxis => Kind != BindKind.Button;
    /// <summary>The label on the live view's button chips.</summary>
    public string Chip { get; init; } = "";
    public string Short => Chip.Length > 0 ? Chip : Key;

    private InputRef? input;
    public InputRef? Input
    {
        get => input;
        set
        {
            input = value;
            if (input == null && extras.Count > 0)
            {
                // The first extra input takes the place of a removed main one.
                input = extras[0];
                extras.RemoveAt(0);
            }
            ChangedInputs();
        }
    }
    public bool IsBound => input != null;

    // A button may have more inputs than one (the game ORs them: "B=lever,B=button"), e.g. a
    // handbrake lever and a rim button that both press B.
    private readonly List<InputRef> extras = new();
    public IReadOnlyList<InputRef> Extras => extras;
    public IEnumerable<InputRef> AllInputs => input == null ? extras : extras.Prepend(input);
    public bool CanAddInput => Kind == BindKind.Button && input != null;

    public void AddInput(InputRef extra)
    {
        if (input == null) { Input = extra; return; }
        if (AllInputs.Any(i => i.SameInput(extra))) return;
        extras.Add(extra);
        ChangedInputs();
    }

    /// <summary>Removes <paramref name="other"/> wherever it is bound here; true if it was.</summary>
    public bool RemoveInput(InputRef other)
    {
        if (input != null && input.SameInput(other)) { Input = null; return true; }
        int i = extras.FindIndex(e => e.SameInput(other));
        if (i < 0) return false;
        extras.RemoveAt(i);
        ChangedInputs();
        return true;
    }

    public void ClearInputs()
    {
        extras.Clear();
        Input = null;
    }

    private void ChangedInputs()
    {
        Changed(nameof(Input)); Changed(nameof(IsBound)); Changed(nameof(BindingText));
        Changed(nameof(Invert)); Changed(nameof(DeviceText)); Changed(nameof(CanAddInput));
    }

    public bool Invert
    {
        get => input?.Inverted ?? false;
        set { if (input != null && input.Inverted != value) { input.Inverted = value; Changed(nameof(Invert)); } }
    }

    public string DeviceText => input == null ? "" :
        input.Device?.Name ?? (input.Unresolved is { } u ? $"{u} (not connected)" : "");
    public string BindingText => input == null ? "Not bound" :
        string.Join("  +  ", AllInputs.Select(i => $"{DeviceName(i)} · {i.Describe()}"));

    private static string DeviceName(InputRef i) =>
        i.Device?.Name ?? (i.Unresolved is { } u ? $"{u} (not connected)" : "");

    // Live state, as the game would see it.
    private double value;
    public double Value { get => value; set { if (Math.Abs(this.value - value) > 0.0005) { this.value = value; Changed(nameof(Value)); } } }
    private string valueText = "";
    public string ValueText { get => valueText; set { if (valueText != value) { valueText = value; Changed(nameof(ValueText)); } } }
    private bool pressed;
    public bool Pressed { get => pressed; set { if (pressed != value) { pressed = value; Changed(nameof(Pressed)); } } }
    private bool isCurrent;
    public bool IsCurrent { get => isCurrent; set { if (isCurrent != value) { isCurrent = value; Changed(nameof(IsCurrent)); } } }

    public event PropertyChangedEventHandler? PropertyChanged;
    public void Changed(string name) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

/// <summary>Everything the setup writes: bindings plus force feedback and tuning settings.</summary>
public sealed class BindingSet
{
    public List<BindingItem> Items { get; } =
    [
        new() { Key = "STEER", Label = "Steering", Kind = BindKind.Steering,
                Prompt = "Turn the wheel to the LEFT, at least a quarter turn, then back to centre." },
        new() { Key = "THROTTLE", Label = "Throttle", Kind = BindKind.Pedal,
                Prompt = "Press the THROTTLE pedal all the way down, then release it." },
        new() { Key = "BRAKE", Label = "Brake", Kind = BindKind.Pedal,
                Prompt = "Press the BRAKE pedal all the way down, then release it." },
        new() { Key = "CLUTCH", Label = "Clutch", Kind = BindKind.Pedal,
                Prompt = "Press the CLUTCH pedal all the way down, then release it. The game reads it as an analog clutch; choose a manual-with-clutch gearbox in the game to use it." },
        // FH1's wheel layout 1, the one it uses for a wheel by default (its WheelLayouts table,
        // traced by Ty Crowther in pinyon-shift PR #605). Each row is the Xbox button the game
        // receives, with what we think it does in FH1 in brackets; drives confirmed the paddles
        // and that Back changes the view. The stick clicks are guesses and carry a "?".
        Button("RB", "RB", "shift up"),
        Button("LB", "LB", "shift down"),
        Button("B", "B", "handbrake"),
        Button("A", "A", "clutch",
               "Only if you want a clutch on a button: a clutch pedal is bound in its own step."),
        Button("Y", "Y", "rewind"),
        Button("X", "X", "activate"),
        Button("BACK", "Back", "view"),
        Button("START", "Start", "pause"),
        Button("LS", "LS", "horn?", "LS is the left stick click."),
        Button("RS", "RS", "look back?", "RS is the right stick click."),
        Button("UP", "D-pad up", null),
        Button("DOWN", "D-pad down", null),
        Button("LEFT", "D-pad left", null),
        Button("RIGHT", "D-pad right", null),
        // An H-pattern shifter, last so a wheel without one skips them all at 1st gear. The
        // game reads the held gear in its wheel path (found by Ty Crowther, pinyon-shift PR #605).
        Gear("GEAR1", "1st", "1",
             "Put the H-shifter in 1st gear. No H-shifter? Click Skip to finish the setup."),
        Gear("GEAR2", "2nd", "2"),
        Gear("GEAR3", "3rd", "3"),
        Gear("GEAR4", "4th", "4"),
        Gear("GEAR5", "5th", "5"),
        Gear("GEAR6", "6th", "6"),
        Gear("GEAR7", "7th", "7", "Put the H-shifter in 7th gear, or click Skip if it has no 7th."),
        Gear("REVERSE", "Reverse", "R"),
    ];

    /// <summary>The first gear step: skipping it unbound ends the guided setup.</summary>
    public const string FirstGear = "GEAR1";

    private static BindingItem Gear(string key, string gear, string chip, string? prompt = null) => new()
    {
        Key = key, Label = $"Shifter {gear}", Kind = BindKind.Button, Chip = chip,
        Prompt = prompt ?? $"Put the H-shifter in {gear.ToLowerInvariant()}" +
                 (key == "REVERSE" ? "." : " gear."),
    };

    private static BindingItem Button(string key, string xbox, string? role, string? note = null) => new()
    {
        Key = key, Label = role == null ? xbox : $"{xbox} ({role})", Kind = BindKind.Button,
        Chip = key switch { "UP" => "↑", "DOWN" => "↓", "LEFT" => "←", "RIGHT" => "→", _ => xbox },
        Prompt = $"Press the button you want for Xbox {xbox.ToUpperInvariant()}" +
                 (role != null ? $" (in FH1 we think: {role.TrimEnd('?')})." : ".") +
                 (role?.EndsWith('?') == true ? " That role is our best guess." : "") +
                 (note != null ? " " + note : "") +
                 " Any device works: the rim, a button box, a shifter, a hat or a lever.",
    };

    public BindingItem Get(string key) => Items.First(i => i.Key == key);
    public BindingItem Steering => Get("STEER");
    public IEnumerable<BindingItem> Pedals => Items.Where(i => i.Kind == BindKind.Pedal);
    public IEnumerable<BindingItem> Buttons => Items.Where(i => i.Kind == BindKind.Button);

    // Force feedback and tuning (wheel_* cvars), with the game's defaults.
    public DeviceKey? FfbDevice { get; set; }
    public string? FfbDeviceUnresolved { get; set; }
    public string FfbMode { get; set; } = "difference";
    public int FfbStrength { get; set; } = 25;
    public bool FfbInvert { get; set; }
    public bool FfbTrace { get; set; }
    public int FfbMinForce { get; set; }
    public int FfbSpring { get; set; } = 100;
    public int FfbDamper { get; set; } = 100;
    public int FfbFriction { get; set; } = 100;
    public int FfbInertia { get; set; } = 100;
    /// <summary>Shares of the game's rumble per motor: FH1's right motor is the engine, the left the road.</summary>
    public int FfbRumbleEngine { get; set; } = 100;
    public int FfbRumbleRoad { get; set; } = 100;
    /// <summary>FH1's effect values are bytes (its spring sent coefficient 63, saturation 127).</summary>
    public int FfbMagnitudeMax { get; set; } = 127;
    public bool Wheel900 { get; set; } = true;
    public int SteeringScale { get; set; } = 100;
    public int SteeringDeadzone { get; set; }
    public int PedalDeadzone { get; set; } = 3;
    /// <summary>Each pedal's dead zones in percent (wheel_{throttle,brake,clutch}_deadzone_{bottom,top}).</summary>
    public Dictionary<string, (int Bottom, int Top)> PedalDeadzones { get; } = new()
    {
        ["THROTTLE"] = (3, 0), ["BRAKE"] = (3, 0), ["CLUTCH"] = (3, 0),
    };

    // The F6 and setup choices: the game's effects (with motor fallback), rumble only, or off.
    public static readonly string[] FfbModes = ["difference", "rumble", "off"];

    // ----------------------------------------------------------------------------------------
    // Live values

    public static Device? Resolve(DeviceKey? key, IEnumerable<Device> devices) =>
        key == null ? null : devices.FirstOrDefault(key.Is);

    public void UpdateLive(IList<Device> devices)
    {
        foreach (var item in Items)
        {
            var dev = Resolve(item.Input?.Device, devices);
            if (item.Input == null || dev == null)
            {
                item.Value = 0;
                item.Pressed = false;
                item.ValueText = "";
                continue;
            }
            Evaluate(item, item.Input, dev, out double value, out bool pressed, out string text);
            foreach (var extra in item.Extras)
            {
                if (pressed || Resolve(extra.Device, devices) is not { } extraDev) continue;
                Evaluate(item, extra, extraDev, out value, out pressed, out text);
            }
            item.Value = value;
            item.Pressed = pressed;
            item.ValueText = text;
        }
    }

    /// <summary>What the game reads from <paramref name="input"/> for <paramref name="item"/>.</summary>
    public void Evaluate(BindingItem item, InputRef input, Device dev, out double value, out bool pressed, out string text)
    {
        value = 0; pressed = false; text = "";
        switch (input.Type)
        {
            case InputType.Axis when input.Index < dev.Axes.Length:
            {
                short raw = dev.Axes[input.Index];
                if (item.Kind == BindKind.Steering)
                {
                    short s = WheelMath.SteeringFromAxis(raw, input.Inverted, SteeringScale, SteeringDeadzone);
                    value = s / 32767.0;
                    text = $"{WheelMath.Signed((int)Math.Round(value * 100))} %";
                }
                else
                {
                    var (bottom, top) = item.Kind == BindKind.Pedal && PedalDeadzones.TryGetValue(item.Key, out var dz)
                        ? dz : (0, 0);
                    byte p = WheelMath.PedalFromAxis(raw, input.Inverted, bottom, top);
                    value = p / 255.0;
                    pressed = p >= 128;
                    text = item.Kind == BindKind.Pedal ? $"{Math.Round(value * 100)} %" : pressed ? "pressed" : "";
                }
                break;
            }
            case InputType.Button when input.Index < dev.Buttons.Length:
                pressed = dev.Buttons[input.Index];
                value = pressed ? 1 : 0;
                text = pressed ? "pressed" : "";
                break;
            case InputType.Hat when input.Index < dev.Hats.Length:
                pressed = (dev.Hats[input.Index] & input.HatMask) != 0;
                value = pressed ? 1 : 0;
                text = pressed ? "pressed" : "";
                break;
        }
    }

    // ----------------------------------------------------------------------------------------
    // Config

    private DeviceKey? steeringDevice;

    /// <summary>Reads the wheel_* keys the game uses, resolving devices against those connected.</summary>
    public void Load(IReadOnlyDictionary<string, string> config, IList<Device> devices)
    {
        string Str(string key, string fallback) => config.TryGetValue(key, out var v) ? v : fallback;
        int Int(string key, int fallback) =>
            config.TryGetValue(key, out var v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int n) ? n : fallback;
        bool Bool(string key, bool fallback) =>
            config.TryGetValue(key, out var v) ? v.Equals("true", StringComparison.OrdinalIgnoreCase) : fallback;

        FfbMode = Str("wheel_ffb_mode", "difference");
        if (!FfbModes.Contains(FfbMode)) FfbMode = "difference";
        FfbStrength = Math.Clamp(Int("wheel_ffb_strength", 25), 0, 100);
        FfbInvert = Bool("wheel_ffb_invert", false);
        FfbTrace = Bool("wheel_ffb_trace", false);
        FfbMinForce = Math.Clamp(Int("wheel_ffb_min_force", 0), 0, 30);
        FfbSpring = Math.Clamp(Int("wheel_ffb_spring", 100), 0, 200);
        FfbDamper = Math.Clamp(Int("wheel_ffb_damper", 100), 0, 200);
        FfbFriction = Math.Clamp(Int("wheel_ffb_friction", 100), 0, 200);
        FfbInertia = Math.Clamp(Int("wheel_ffb_inertia", 100), 0, 200);
        FfbRumbleEngine = Math.Clamp(Int("wheel_ffb_rumble_engine", 100), 0, 100);
        FfbRumbleRoad = Math.Clamp(Int("wheel_ffb_rumble_road", 100), 0, 100);
        FfbMagnitudeMax = Math.Clamp(Int("wheel_ffb_magnitude_max", 127), 1, 1000000);
        Wheel900 = Bool("wheel_900_degree", true);
        SteeringScale = Math.Clamp(Int("wheel_steering_scale", 100), 10, 1000);
        SteeringDeadzone = Math.Clamp(Int("wheel_steering_deadzone", 0), 0, 50);
        PedalDeadzone = Math.Clamp(Int("wheel_pedal_deadzone", 3), 0, 50);
        foreach (var (key, cvar) in new[] { ("THROTTLE", "throttle"), ("BRAKE", "brake"), ("CLUTCH", "clutch") })
        {
            int bottom = Int($"wheel_{cvar}_deadzone_bottom", -1);
            PedalDeadzones[key] = (bottom < 0 ? PedalDeadzone : Math.Clamp(bottom, 0, 50),
                                   Math.Clamp(Int($"wheel_{cvar}_deadzone_top", 0), 0, 50));
        }

        string wheel = Str("wheel_device", "");
        Device? steer = wheel.Length > 0 ? devices.FirstOrDefault(d => WheelMath.DeviceMatches(wheel, d.Name, d.Vendor, d.Product, d.Path)) : null;
        steeringDevice = steer != null ? DeviceKey.Of(steer) : null;
        if (wheel.Length > 0)
        {
            Steering.Input = new InputRef
            {
                Device = steeringDevice,
                Unresolved = steer == null ? wheel : null,
                Type = InputType.Axis,
                Index = Math.Clamp(Int("wheel_steering_axis", 0), 0, 15),
                Inverted = Bool("wheel_steering_invert", false),
            };
        }

        foreach (var (key, cvar) in new[] { ("THROTTLE", "wheel_throttle"), ("BRAKE", "wheel_brake"), ("CLUTCH", "wheel_clutch") })
            Get(key).Input = ParseAxis(Str(cvar, ""), devices, wheel);

        foreach (var b in Buttons) b.ClearInputs();
        string buttons = Str("wheel_buttons", "UP=h0.up,DOWN=h0.down,LEFT=h0.left,RIGHT=h0.right");
        string? target = null;
        foreach (string rawPart in buttons.Split(','))
        {
            string part = rawPart.Trim();
            if (part.Length == 0) continue;
            string text = part;
            int eq = part.IndexOf('=');
            if (eq >= 0)
            {
                target = part[..eq].Trim().ToUpperInvariant();
                text = part[(eq + 1)..];
            }
            if (target == null || Items.FirstOrDefault(i => i.Key == target && i.Kind == BindKind.Button) is not { } item) continue;
            if (ParseButton(text, devices, wheel) is { } parsed) item.AddInput(parsed);
        }

        string ffb = Str("wheel_ffb_device", "");
        var ffbDev = ffb.Length > 0 ? devices.FirstOrDefault(d => WheelMath.DeviceMatches(ffb, d.Name, d.Vendor, d.Product, d.Path)) : null;
        FfbDevice = ffbDev != null ? DeviceKey.Of(ffbDev) : null;
        FfbDeviceUnresolved = ffb.Length > 0 && ffbDev == null ? ffb : null;
    }

    private static (DeviceKey? key, string? unresolved) ResolveText(string device, IList<Device> devices, string wheel)
    {
        string match = device.Length > 0 ? device : wheel;
        if (match.Length == 0) return (null, null);
        var dev = devices.FirstOrDefault(d => WheelMath.DeviceMatches(match, d.Name, d.Vendor, d.Product, d.Path));
        return dev != null ? (DeviceKey.Of(dev), null) : (null, match);
    }

    private static (string device, string rest) SplitDevice(string text)
    {
        int bar = text.LastIndexOf('|');
        return bar < 0 ? ("", text.Trim()) : (text[..bar].Trim(), text[(bar + 1)..].Trim());
    }

    private static InputRef? ParseAxis(string text, IList<Device> devices, string wheel)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;
        var (device, rest) = SplitDevice(text);
        bool inverted = false;
        if (rest.StartsWith('+') || rest.StartsWith('-'))
        {
            inverted = rest[0] == '-';
            rest = rest[1..];
        }
        if (rest.StartsWith("axis", StringComparison.OrdinalIgnoreCase)) rest = rest[4..];
        else if (rest.StartsWith("a", StringComparison.OrdinalIgnoreCase)) rest = rest[1..];
        else return null;
        if (!int.TryParse(rest, out int index)) return null;
        var (key, unresolved) = ResolveText(device, devices, wheel);
        return new InputRef { Device = key, Unresolved = unresolved, Type = InputType.Axis, Index = index, Inverted = inverted };
    }

    private static InputRef? ParseButton(string text, IList<Device> devices, string wheel)
    {
        var (device, rest) = SplitDevice(text);
        var (key, unresolved) = ResolveText(device, devices, wheel);
        string axisText = rest;
        bool inverted = false;
        if (axisText.StartsWith('+') || axisText.StartsWith('-'))
        {
            inverted = axisText[0] == '-';
            axisText = axisText[1..];
        }
        if (axisText.StartsWith("axis", StringComparison.OrdinalIgnoreCase) && int.TryParse(axisText[4..], out int axis))
            return new InputRef { Device = key, Unresolved = unresolved, Type = InputType.Axis, Index = axis, Inverted = inverted };
        if (rest.StartsWith("h", StringComparison.OrdinalIgnoreCase))
        {
            int dot = rest.IndexOf('.');
            if (dot < 0 || !int.TryParse(rest[1..dot], out int hat)) return null;
            byte mask = WheelMath.HatFromName(rest[(dot + 1)..]);
            return mask == 0 ? null : new InputRef { Device = key, Unresolved = unresolved, Type = InputType.Hat, Index = hat, HatMask = mask };
        }
        if (rest.StartsWith("b", StringComparison.OrdinalIgnoreCase)) rest = rest[1..];
        return int.TryParse(rest, out int button)
            ? new InputRef { Device = key, Unresolved = unresolved, Type = InputType.Button, Index = button }
            : null;
    }

    private static string Match(DeviceKey? key, string? unresolved, IList<Device> devices)
    {
        var dev = Resolve(key, devices);
        if (dev != null) return WheelMath.DeviceMatch(dev, devices);
        if (unresolved != null) return unresolved;
        if (key == null) return "";
        return key.Path.Length > 0 ? "path:" + key.Path : key.Name;
    }

    private string Prefix(InputRef input, IList<Device> devices)
    {
        var steer = Steering.Input;
        bool sameAsSteering = steer != null &&
            (input.Device != null ? input.Device == steer.Device : input.Unresolved == steer.Unresolved);
        return sameAsSteering ? "" : Match(input.Device, input.Unresolved, devices) + "|";
    }

    private string AxisText(InputRef? input, IList<Device> devices) => input == null ? "" :
        Prefix(input, devices) + (input.Inverted ? "-" : "+") + "axis" + input.Index;

    private string ButtonText(InputRef input, IList<Device> devices) =>
        Prefix(input, devices) + input.Type switch
        {
            InputType.Axis => (input.Inverted ? "-" : "+") + "axis" + input.Index,
            InputType.Hat => $"h{input.Index}.{WheelMath.HatName(input.HatMask)}",
            _ => input.Index.ToString(CultureInfo.InvariantCulture),
        };

    public static string TomlString(string value) =>
        "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

    /// <summary>The wheel_* lines for pinyon_shift.toml. Steering must be bound.</summary>
    public List<(string Key, string Value)> ConfigLines(IList<Device> devices)
    {
        var steer = Steering.Input!;
        var buttons = string.Join(",", Buttons.SelectMany(b => b.AllInputs.Select(i => $"{b.Key}={ButtonText(i, devices)}")));
        string ffbDevice = FfbDevice != null || FfbDeviceUnresolved != null ? Match(FfbDevice, FfbDeviceUnresolved, devices) : "";
        return
        [
            ("wheel_enabled", "true"),
            ("wheel_device", TomlString(Match(steer.Device, steer.Unresolved, devices))),
            ("wheel_steering_axis", steer.Index.ToString(CultureInfo.InvariantCulture)),
            ("wheel_steering_invert", steer.Inverted ? "true" : "false"),
            ("wheel_throttle", TomlString(AxisText(Get("THROTTLE").Input, devices))),
            ("wheel_brake", TomlString(AxisText(Get("BRAKE").Input, devices))),
            ("wheel_clutch", TomlString(AxisText(Get("CLUTCH").Input, devices))),
            ("wheel_buttons", TomlString(buttons)),
            ("wheel_ffb_device", TomlString(ffbDevice)),
            ("wheel_hide_gamepads", "true"),
            ("wheel_ffb_mode", TomlString(FfbMode)),
            ("wheel_ffb_strength", FfbStrength.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_invert", FfbInvert ? "true" : "false"),
            ("wheel_ffb_trace", FfbTrace ? "true" : "false"),
            ("wheel_ffb_min_force", FfbMinForce.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_spring", FfbSpring.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_damper", FfbDamper.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_friction", FfbFriction.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_inertia", FfbInertia.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_rumble_engine", FfbRumbleEngine.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_rumble_road", FfbRumbleRoad.ToString(CultureInfo.InvariantCulture)),
            ("wheel_ffb_magnitude_max", FfbMagnitudeMax.ToString(CultureInfo.InvariantCulture)),
            ("wheel_900_degree", Wheel900 ? "true" : "false"),
            ("wheel_steering_scale", SteeringScale.ToString(CultureInfo.InvariantCulture)),
            ("wheel_steering_deadzone", SteeringDeadzone.ToString(CultureInfo.InvariantCulture)),
            ("wheel_pedal_deadzone", PedalDeadzone.ToString(CultureInfo.InvariantCulture)),
            ("wheel_throttle_deadzone_bottom", PedalDeadzones["THROTTLE"].Bottom.ToString(CultureInfo.InvariantCulture)),
            ("wheel_throttle_deadzone_top", PedalDeadzones["THROTTLE"].Top.ToString(CultureInfo.InvariantCulture)),
            ("wheel_brake_deadzone_bottom", PedalDeadzones["BRAKE"].Bottom.ToString(CultureInfo.InvariantCulture)),
            ("wheel_brake_deadzone_top", PedalDeadzones["BRAKE"].Top.ToString(CultureInfo.InvariantCulture)),
            ("wheel_clutch_deadzone_bottom", PedalDeadzones["CLUTCH"].Bottom.ToString(CultureInfo.InvariantCulture)),
            ("wheel_clutch_deadzone_top", PedalDeadzones["CLUTCH"].Top.ToString(CultureInfo.InvariantCulture)),
        ];
    }
}
