using PinyonShift.Launcher.Wheel.Input;

namespace PinyonShift.Launcher.Wheel.Bindings;

/// <summary>
/// Listens for the input a step asks for: the axis that moves furthest (steering, pedals), or the
/// first button, hat direction or lever axis pressed after the step began.
/// </summary>
public sealed class Capture
{
    private readonly BindingSet set;
    private readonly DeviceManager devices;
    public BindingItem Item { get; }

    public InputRef? Candidate { get; private set; }
    public uint CandidateDevice { get; private set; }
    public short Rest { get; private set; }
    private short peak;
    private bool userSetInvert;

    public bool Detected => Candidate != null;

    public Capture(BindingSet set, DeviceManager devices, BindingItem item)
    {
        this.set = set;
        this.devices = devices;
        Item = item;
        Reset();
    }

    public void Reset()
    {
        devices.SnapshotBaselines();
        Candidate = null;
        CandidateDevice = 0;
        userSetInvert = false;
    }

    public void SetInvert(bool inverted)
    {
        if (Candidate == null) return;
        Candidate.Inverted = inverted;
        userSetInvert = true;
    }

    /// <summary>An axis already used by steering or another pedal is not offered again.</summary>
    private bool AxisTaken(Device d, int axis)
    {
        foreach (var other in set.Items)
        {
            if (other == Item || other.Kind == BindKind.Button || other.Input is not { Type: InputType.Axis } input) continue;
            if (input.Index == axis && input.Device != null && input.Device.Is(d)) return true;
        }
        return false;
    }

    public void Update()
    {
        if (Item.Kind == BindKind.Button) TrackButtons();
        else TrackAxes(Item.Kind == BindKind.Steering ? 10000 : 16000);
    }

    private void TrackAxes(int threshold)
    {
        if (Candidate != null)
        {
            // Follow the detected axis to its full travel; the direction comes from that.
            var dev = devices.Find(CandidateDevice);
            if (dev != null && Candidate.Index < dev.Axes.Length)
            {
                short value = dev.Axes[Candidate.Index];
                if (Math.Abs(value - Rest) > Math.Abs(peak - Rest)) peak = value;
                if (!userSetInvert) Candidate.Inverted = DirectionFromPeak();
            }
            return;
        }
        int best = 0;
        Device? bestDev = null;
        int bestAxis = -1;
        foreach (var d in devices.Devices)
        {
            for (int i = 0; i < d.Axes.Length && i < d.BaseAxes.Length; i++)
            {
                if (AxisTaken(d, i)) continue;
                int delta = d.Axes[i] - d.BaseAxes[i];
                if (Math.Abs(delta) > Math.Abs(best))
                {
                    best = delta;
                    bestDev = d;
                    bestAxis = i;
                }
            }
        }
        if (bestDev == null || Math.Abs(best) < threshold) return;
        CandidateDevice = bestDev.Id;
        Rest = bestDev.BaseAxes[bestAxis];
        peak = bestDev.Axes[bestAxis];
        Candidate = new InputRef
        {
            Device = DeviceKey.Of(bestDev),
            Type = InputType.Axis,
            Index = bestAxis,
            Inverted = DirectionFromPeak(),
        };
    }

    /// <summary>Steering: the player turned left, which the game wants negative. Pedals: pressing
    /// should raise the value; a pedal that falls when pressed is inverted.</summary>
    private bool DirectionFromPeak() => Item.Kind == BindKind.Steering ? peak > Rest : peak < Rest;

    private void TrackButtons()
    {
        if (Candidate != null) return;
        foreach (var d in devices.Devices)
        {
            // A button or hat held when the step began (an H-shifter left in gear) counts again
            // once it is let go, so moving the shifter out of the gate and back binds it.
            for (int i = 0; i < d.Buttons.Length && i < d.BaseButtons.Length; i++)
                if (!d.Buttons[i]) d.BaseButtons[i] = false;
            for (int i = 0; i < d.Hats.Length && i < d.BaseHats.Length; i++)
                d.BaseHats[i] &= d.Hats[i];
            for (int i = 0; i < d.Buttons.Length && i < d.BaseButtons.Length; i++)
            {
                if (d.Buttons[i] && !d.BaseButtons[i])
                {
                    Found(d, new InputRef { Device = DeviceKey.Of(d), Type = InputType.Button, Index = i });
                    return;
                }
            }
            for (int i = 0; i < d.Hats.Length && i < d.BaseHats.Length; i++)
            {
                byte pressed = (byte)(d.Hats[i] & ~d.BaseHats[i]);
                if (pressed != 0)
                {
                    Found(d, new InputRef { Device = DeviceKey.Of(d), Type = InputType.Hat, Index = i, HatMask = WheelMath.FirstHatBit(pressed) });
                    return;
                }
            }
            for (int i = 0; i < d.Axes.Length && i < d.BaseAxes.Length; i++)
            {
                if (AxisTaken(d, i)) continue;
                int delta = d.Axes[i] - d.BaseAxes[i];
                if (Math.Abs(delta) >= 24000)
                {
                    Rest = d.BaseAxes[i];
                    Found(d, new InputRef { Device = DeviceKey.Of(d), Type = InputType.Axis, Index = i, Inverted = delta < 0 });
                    return;
                }
            }
        }
    }

    private void Found(Device d, InputRef input)
    {
        CandidateDevice = d.Id;
        Candidate = input;
    }

    /// <summary>The detected input is back at rest: a button or hat let go, an axis returned.</summary>
    public bool CandidateReleased()
    {
        if (Candidate == null || devices.Find(CandidateDevice) is not { } d) return false;
        return Candidate.Type switch
        {
            InputType.Button => Candidate.Index < d.Buttons.Length && !d.Buttons[Candidate.Index],
            InputType.Hat => Candidate.Index < d.Hats.Length && (d.Hats[Candidate.Index] & Candidate.HatMask) == 0,
            _ => Candidate.Index < d.Axes.Length && Math.Abs(d.Axes[Candidate.Index] - Rest) < 3000,
        };
    }

    /// <summary>An axis resting mid-range reads as half pressed in the game.</summary>
    public bool RestsMidRange =>
        Candidate is { Type: InputType.Axis } && Item.Kind != BindKind.Steering && Math.Abs((int)Rest) < 12000;
}
