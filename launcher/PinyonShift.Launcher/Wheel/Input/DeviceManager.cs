using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using PinyonShift.Launcher.Wheel.Diagnostics;

namespace PinyonShift.Launcher.Wheel.Input;

/// <summary>One SDL joystick, opened raw the way the game's wheel driver opens it.</summary>
public sealed class Device : INotifyPropertyChanged
{
    public uint Id { get; init; }
    public IntPtr Handle { get; init; }
    public string Name { get; init; } = "";
    public string Path { get; init; } = "";
    public ushort Vendor { get; init; }
    public ushort Product { get; init; }
    public bool Haptic { get; init; }

    public short[] Axes { get; init; } = [];
    public bool[] Buttons { get; init; } = [];
    public byte[] Hats { get; init; } = [];
    public short[] BaseAxes { get; set; } = [];
    public bool[] BaseButtons { get; set; } = [];
    public byte[] BaseHats { get; set; } = [];
    // Last values the activity display saw. Each is sized on its own: a button box has
    // buttons but no axes.
    private short[] prevAxes = [];
    private bool[] prevButtons = [];
    private byte[] prevHats = [];
    private DateTime nextActivityLog;

    public string Ids => $"{Vendor:x4}:{Product:x4}";
    public string Summary =>
        $"{Ids} · {Axes.Length} axes · {Buttons.Length} buttons" +
        (Hats.Length > 0 ? $" · {Hats.Length} hat{(Hats.Length > 1 ? "s" : "")}" : "") +
        (Haptic ? " · force feedback" : "");

    private string activity = "";
    public string Activity { get => activity; private set { if (activity != value) { activity = value; Changed(nameof(Activity)); } } }
    private bool isActive;
    /// <summary>Moved in the last 1.5 s.</summary>
    public bool IsActive { get => isActive; private set { if (isActive != value) { isActive = value; Changed(nameof(IsActive)); } } }
    private DateTime activeUntil;

    public event PropertyChangedEventHandler? PropertyChanged;
    private void Changed(string name) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public void Read()
    {
        for (int i = 0; i < Axes.Length; i++) Axes[i] = Sdl.SDL_GetJoystickAxis(Handle, i);
        for (int i = 0; i < Buttons.Length; i++) Buttons[i] = Sdl.SDL_GetJoystickButton(Handle, i);
        for (int i = 0; i < Hats.Length; i++) Hats[i] = Sdl.SDL_GetJoystickHat(Handle, i);
    }

    public void SnapshotBaseline()
    {
        BaseAxes = (short[])Axes.Clone();
        BaseButtons = (bool[])Buttons.Clone();
        BaseHats = (byte[])Hats.Clone();
    }

    public void InitActivity()
    {
        prevAxes = (short[])Axes.Clone();
        prevButtons = (bool[])Buttons.Clone();
        prevHats = (byte[])Hats.Clone();
    }

    public void TrackActivity(DateTime now)
    {
        if (prevAxes.Length != Axes.Length || prevButtons.Length != Buttons.Length || prevHats.Length != Hats.Length)
            InitActivity();
        string? what = null;
        for (int i = 0; i < Axes.Length; i++)
        {
            if (Math.Abs(Axes[i] - prevAxes[i]) > 2500)
            {
                what = $"axis {i}  {WheelMath.Signed(Axes[i])}";
                prevAxes[i] = Axes[i];
            }
        }
        for (int i = 0; i < Buttons.Length; i++)
        {
            if (Buttons[i] != prevButtons[i])
            {
                what = $"button {i} {(Buttons[i] ? "down" : "up")}";
                prevButtons[i] = Buttons[i];
            }
        }
        for (int i = 0; i < Hats.Length; i++)
        {
            if (Hats[i] != prevHats[i])
            {
                what = $"hat {i} {(Hats[i] == 0 ? "centre" : WheelMath.HatName(WheelMath.FirstHatBit(Hats[i])))}";
                prevHats[i] = Hats[i];
            }
        }
        if (what != null)
        {
            Activity = what;
            activeUntil = now.AddSeconds(1.5);
            if (now >= nextActivityLog)
            {
                Log.Write($"input: \"{Name}\" {what}");
                nextActivityLog = now.AddMilliseconds(500);
            }
        }
        IsActive = now < activeUntil;
    }
}

/// <summary>
/// Polls SDL joysticks from the UI thread. SDL is built from the game SDK's own source with the
/// same joystick defaults, so names, paths and axis/button numbers match what the game reads.
/// </summary>
public sealed class DeviceManager : IDisposable
{
    public ObservableCollection<Device> Devices { get; } = [];
    public string? InitError { get; private set; }
    public event Action? DevicesChanged;
    private DateTime nextScan;
    private readonly HashSet<string> reportedErrors = [];
    private bool started;

    public bool Start()
    {
        try
        {
            // The setup window is not an SDL window, so SDL must not treat input as unfocused.
            Log.Step("SDL_SetHint");
            Sdl.SDL_SetHint("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
            Log.Write("SDL_Init(joystick, haptic)...");
            Log.Step("SDL_Init");
            var watch = Stopwatch.StartNew();
            if (!Sdl.SDL_Init(Sdl.InitJoystick | Sdl.InitHaptic))
            {
                InitError = "SDL could not start: " + Sdl.Error();
                Log.Write(InitError);
                return false;
            }
            Log.Write($"SDL_Init done in {watch.ElapsedMilliseconds} ms");
        }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException or BadImageFormatException)
        {
            InitError = "SDL3.dll could not be loaded: " + e.Message;
            Log.Error("loading SDL3.dll", e);
            return false;
        }
        started = true;
        Scan();
        return true;
    }

    /// <summary>Call ~60 times a second.</summary>
    public void Poll()
    {
        if (!started) return;
        Log.Step("SDL_UpdateJoysticks");
        Sdl.SDL_UpdateJoysticks();
        Log.Step("SDL_FlushEvents");
        Sdl.SDL_FlushEvents(0, uint.MaxValue);
        var now = DateTime.UtcNow;
        if (now >= nextScan) Scan();
        foreach (var d in Devices)
        {
            try
            {
                Log.Step($"reading \"{d.Name}\"");
                d.Read();
                d.TrackActivity(now);
            }
            catch (Exception e)
            {
                // One device's problem must not stop the others being read.
                if (reportedErrors.Add($"{d.Id}:{e.GetType().Name}")) Log.Error($"reading \"{d.Name}\"", e);
            }
        }
        Log.Step("idle");
    }

    public Device? Find(uint id) => Devices.FirstOrDefault(d => d.Id == id);

    public void SnapshotBaselines()
    {
        foreach (var d in Devices) d.SnapshotBaseline();
    }

    private void Scan()
    {
        nextScan = DateTime.UtcNow.AddMilliseconds(500);
        var ids = new List<uint>();
        Log.Step("SDL_GetJoysticks");
        IntPtr list = Sdl.SDL_GetJoysticks(out int count);
        if (list != IntPtr.Zero)
        {
            for (int i = 0; i < count; i++) ids.Add((uint)Marshal.ReadInt32(list, i * 4));
            Sdl.SDL_free(list);
        }
        bool changed = false;
        foreach (var gone in Devices.Where(d => !ids.Contains(d.Id)).ToList())
        {
            Log.Write($"device removed: id {gone.Id} \"{gone.Name}\"");
            Log.Step($"closing \"{gone.Name}\"");
            Sdl.SDL_CloseJoystick(gone.Handle);
            Devices.Remove(gone);
            changed = true;
        }
        foreach (uint id in ids)
        {
            if (Find(id) != null) continue;
            var d = OpenDevice(id);
            if (d == null) continue;
            Devices.Add(d);
            changed = true;
        }
        if (changed)
        {
            Log.Write($"devices now: {Devices.Count}");
            DevicesChanged?.Invoke();
        }
        Log.Step("idle");
    }

    private Device? OpenDevice(uint id)
    {
        var watch = Stopwatch.StartNew();
        Log.Write($"opening device id {id}...");
        Log.Step($"SDL_OpenJoystick({id})");
        IntPtr js = Sdl.SDL_OpenJoystick(id);
        if (js == IntPtr.Zero)
        {
            Log.Write($"  could not open id {id}: {Sdl.Error()}");
            return null;
        }
        string name = Sdl.Name(js);
        string path = Sdl.Path(js);
        int axes = Math.Max(0, Sdl.SDL_GetNumJoystickAxes(js));
        int buttons = Math.Max(0, Sdl.SDL_GetNumJoystickButtons(js));
        int hats = Math.Max(0, Sdl.SDL_GetNumJoystickHats(js));
        ushort vendor = Sdl.SDL_GetJoystickVendor(js);
        ushort product = Sdl.SDL_GetJoystickProduct(js);
        Log.Write($"  opened \"{name}\" {vendor:x4}:{product:x4}, {axes} axes, {buttons} buttons, {hats} hats, " +
                  $"path {path} ({watch.ElapsedMilliseconds} ms)");
        Log.Step($"SDL_IsJoystickHaptic(\"{name}\")");
        var hapticWatch = Stopwatch.StartNew();
        bool haptic = false;
        try { haptic = Sdl.SDL_IsJoystickHaptic(js); }
        catch (Exception e) { Log.Error($"haptic check for \"{name}\"", e); }
        Log.Write($"  force feedback: {(haptic ? "yes" : "no")} ({hapticWatch.ElapsedMilliseconds} ms)");
        var d = new Device
        {
            Id = id,
            Handle = js,
            Name = name,
            Path = path,
            Vendor = vendor,
            Product = product,
            Haptic = haptic,
            Axes = new short[axes],
            Buttons = new bool[buttons],
            Hats = new byte[hats],
        };
        try
        {
            d.Read();
            d.SnapshotBaseline();
            d.InitActivity();
            if (axes > 0)
                Log.Write($"  axes at rest: {string.Join(' ', d.Axes.Select(a => a.ToString()))}");
        }
        catch (Exception e)
        {
            Log.Error($"first read of \"{name}\"", e);
        }
        return d;
    }

    /// <summary>A gentle pull LEFT, then RIGHT, with the same direction the game's forces get, so it also
    /// checks Reverse force direction: a positive SDL steering force pulls right (the game's force,
    /// negated for DirectInput, opposes the steering).</summary>
    public async Task<string> TestForceAsync(Device device, bool reverse)
    {
        Log.Write($"FFB test on \"{device.Name}\"");
        Log.Step($"SDL_OpenHapticFromJoystick(\"{device.Name}\")");
        IntPtr haptic = Sdl.SDL_OpenHapticFromJoystick(device.Handle);
        Log.Step("idle");
        if (haptic == IntPtr.Zero)
        {
            string error = "Could not open force feedback: " + Sdl.Error();
            Log.Write("  " + error);
            return error;
        }
        try
        {
            uint features = Sdl.SDL_GetHapticFeatures(haptic);
            Log.Write($"  haptic features 0x{features:X}");
            if ((features & Sdl.HapticConstant) == 0)
                return $"\"{device.Name}\" has no constant force; the game would only rumble it.";
            // SDL's (and DirectInput's) constant force names the side it comes from, so a
            // positive level pulls left. The game's forces go out in that convention too,
            // so Test and play agree and Reverse flips both. A T248 pulled right on -4900.
            short left = (short)(reverse ? -4900 : 4900);  // 15 %
            foreach (short level in new short[] { left, (short)-left })
            {
                int effect = Sdl.SDL_CreateHapticEffect(haptic, Sdl.ConstantForce(level, 500));
                if (effect < 0)
                {
                    string error = "The device refused a constant force: " + Sdl.Error();
                    Log.Write("  " + error);
                    return error;
                }
                bool ran = Sdl.SDL_RunHapticEffect(haptic, effect, 1);
                Log.Write($"  constant force {level}: run {(ran ? "ok" : "failed: " + Sdl.Error())}");
                await Task.Delay(650);
                Sdl.SDL_DestroyHapticEffect(haptic, effect);
            }
            return $"Pulled \"{device.Name}\" LEFT, then RIGHT (15 %). If it pulled right first, tick Reverse force direction.";
        }
        finally
        {
            Sdl.SDL_CloseHaptic(haptic);
        }
    }

    public void Dispose()
    {
        foreach (var d in Devices) Sdl.SDL_CloseJoystick(d.Handle);
        Devices.Clear();
        try { Sdl.SDL_Quit(); } catch (DllNotFoundException) { }
        // The launcher closes and opens the wheel screen; Start initialises SDL again.
        started = false;
        Log.Write("closed");
    }
}
