namespace PinyonShift.Launcher.Wheel.Input;

/// <summary>
/// The game's wheel math, ported from shiftglue-sdk src/input/sdl/wheel_mapping.cpp, so the live
/// view shows exactly what the game will receive.
/// </summary>
public static class WheelMath
{
    public const byte HatUp = 1, HatRight = 2, HatDown = 4, HatLeft = 8;

    /// <summary>Steering axis to the guest's left stick X (−32767..32767).</summary>
    public static short SteeringFromAxis(short raw, bool invert, int scalePercent, int deadzonePercent)
    {
        int value = raw;
        if (invert) value = -value - 1;
        int deadzone = Math.Clamp(deadzonePercent, 0, 50) * 32767 / 100;
        int magnitude = Math.Abs(value);
        if (magnitude <= deadzone) return 0;
        long scaled = (long)(magnitude - deadzone) * 32767 / (32767 - deadzone);
        scaled = scaled * Math.Clamp(scalePercent, 10, 1000) / 100;
        scaled = Math.Min(scaled, 32767);
        return (short)(value < 0 ? -scaled : scaled);
    }

    /// <summary>A pedal axis to a trigger value, 0 at rest and 255 fully pressed.</summary>
    public static byte PedalFromAxis(short raw, bool inverted, int deadzonePercent)
    {
        int travel = raw + 32768;  // 0..65535
        if (inverted) travel = 65535 - travel;
        int deadzone = Math.Clamp(deadzonePercent, 0, 50) * 65535 / 100;
        if (travel <= deadzone) return 0;
        int value = (travel - deadzone) * 255 / (65535 - deadzone);
        return (byte)Math.Clamp(value, 0, 255);
    }

    /// <summary>A pedal with a dead zone at each end (the SDK's two-sided PedalFromAxis).</summary>
    public static byte PedalFromAxis(short raw, bool inverted, int bottomPercent, int topPercent)
    {
        int travel = raw + 32768;
        if (inverted) travel = 65535 - travel;
        int bottom = Math.Clamp(bottomPercent, 0, 50) * 65535 / 100;
        int top = Math.Clamp(topPercent, 0, 50) * 65535 / 100;
        int span = Math.Max(65535 - bottom - top, 1);
        if (travel <= bottom) return 0;
        if (travel >= 65535 - top) return 255;
        return (byte)Math.Clamp((travel - bottom) * 255 / span, 0, 255);
    }

    /// <summary>The game's device match: "vvvv:pppp", "path:&lt;path&gt;" or a name substring.</summary>
    public static bool DeviceMatches(string match, string name, ushort vendor, ushort product, string path)
    {
        match = match.Trim();
        if (match.Length == 0) return true;
        if (match.StartsWith("path:", StringComparison.OrdinalIgnoreCase))
            return path.Length > 0 && string.Equals(match[5..].Trim(), path, StringComparison.OrdinalIgnoreCase);
        if (match.Length == 9 && match[4] == ':' &&
            ushort.TryParse(match[..4], System.Globalization.NumberStyles.HexNumber, null, out ushort v) &&
            ushort.TryParse(match[5..], System.Globalization.NumberStyles.HexNumber, null, out ushort p))
            return v == vendor && p == product;
        return name.Contains(match, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>The shortest text that names exactly this device among those connected.</summary>
    public static string DeviceMatch(Device device, IEnumerable<Device> all)
    {
        var devices = all.ToList();
        if (device.Vendor != 0 || device.Product != 0)
        {
            if (devices.Count(d => d.Vendor == device.Vendor && d.Product == device.Product) <= 1)
                return device.Ids;
        }
        string name = device.Name;
        if (name.Length > 0 && name.IndexOfAny(['|', ',', '=']) < 0 &&
            devices.Count(d => d.Name.Contains(name, StringComparison.OrdinalIgnoreCase)) <= 1)
            return name;
        return "path:" + device.Path;
    }

    public static string HatName(byte mask) => mask switch
    {
        HatUp => "up",
        HatRight => "right",
        HatDown => "down",
        HatLeft => "left",
        _ => "?",
    };

    public static byte HatFromName(string name) => name.Trim().ToLowerInvariant() switch
    {
        "up" or "1" => HatUp,
        "right" or "2" => HatRight,
        "down" or "4" => HatDown,
        "left" or "8" => HatLeft,
        _ => 0,
    };

    public static byte FirstHatBit(byte value)
    {
        foreach (byte bit in new[] { HatUp, HatRight, HatDown, HatLeft })
            if ((value & bit) != 0) return bit;
        return 0;
    }

    /// <summary>A signed number with a real minus sign.</summary>
    public static string Signed(int value) => value < 0 ? "−" + (-(long)value) : value.ToString();
}
