using System.Runtime.InteropServices;

namespace PinyonShift.Launcher.Wheel.Input;

/// <summary>The few SDL3 calls the setup needs: joysticks, haptics and virtual devices (self-test).</summary>
internal static class Sdl
{
    private const string Lib = "SDL3";

    public const uint InitJoystick = 0x200;
    public const uint InitHaptic = 0x1000;
    public const uint HapticConstant = 1;
    public const byte HapticSteeringAxis = 3;
    public const ushort JoystickTypeWheel = 2;
    public const ushort JoystickTypeUnknown = 0;

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_SetHint([MarshalAs(UnmanagedType.LPUTF8Str)] string name,
                                          [MarshalAs(UnmanagedType.LPUTF8Str)] string value);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_Init(uint flags);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_Quit();

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr SDL_GetError();

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern IntPtr SDL_GetJoysticks(out int count);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_free(IntPtr memory);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern IntPtr SDL_OpenJoystick(uint instanceId);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_CloseJoystick(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr SDL_GetJoystickName(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr SDL_GetJoystickPath(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern ushort SDL_GetJoystickVendor(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern ushort SDL_GetJoystickProduct(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern int SDL_GetNumJoystickAxes(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern int SDL_GetNumJoystickButtons(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern int SDL_GetNumJoystickHats(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern short SDL_GetJoystickAxis(IntPtr joystick, int axis);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_GetJoystickButton(IntPtr joystick, int button);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern byte SDL_GetJoystickHat(IntPtr joystick, int hat);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_IsJoystickHaptic(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_UpdateJoysticks();

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_FlushEvents(uint minType, uint maxType);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern IntPtr SDL_OpenHapticFromJoystick(IntPtr joystick);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_CloseHaptic(IntPtr haptic);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern uint SDL_GetHapticFeatures(IntPtr haptic);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern int SDL_CreateHapticEffect(IntPtr haptic, byte[] effect);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_RunHapticEffect(IntPtr haptic, int effect, uint iterations);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern void SDL_DestroyHapticEffect(IntPtr haptic, int effect);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    public static extern uint SDL_AttachVirtualJoystick(IntPtr desc);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_SetJoystickVirtualAxis(IntPtr joystick, int axis, short value);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_SetJoystickVirtualButton(IntPtr joystick, int button,
                                                           [MarshalAs(UnmanagedType.U1)] bool down);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool SDL_SetJoystickVirtualHat(IntPtr joystick, int hat, byte value);

    public static string Error() => Utf8(SDL_GetError());
    public static string Name(IntPtr joystick) => Utf8(SDL_GetJoystickName(joystick));
    public static string Path(IntPtr joystick) => Utf8(SDL_GetJoystickPath(joystick));

    private static string Utf8(IntPtr text) =>
        text == IntPtr.Zero ? "" : Marshal.PtrToStringUTF8(text) ?? "";

    /// <summary>A constant force on the steering axis, laid out as SDL_HapticEffect (72 bytes;
    /// type at 0, direction type at 4, length at 20, level at 30).</summary>
    public static byte[] ConstantForce(short level, uint lengthMs)
    {
        var effect = new byte[72];
        BitConverter.GetBytes((ushort)HapticConstant).CopyTo(effect, 0);
        effect[4] = HapticSteeringAxis;
        BitConverter.GetBytes(lengthMs).CopyTo(effect, 20);
        BitConverter.GetBytes(level).CopyTo(effect, 30);
        return effect;
    }

    /// <summary>Plugs in an SDL virtual joystick (SDL_VirtualJoystickDesc, 136 bytes). Self-test only.</summary>
    public static uint AttachVirtual(string name, ushort vendor, ushort product, ushort type,
                                     int axes, int buttons, int hats)
    {
        IntPtr desc = Marshal.AllocHGlobal(136);
        IntPtr namePtr = Marshal.StringToCoTaskMemUTF8(name);
        try
        {
            for (int i = 0; i < 136; i++) Marshal.WriteByte(desc, i, 0);
            Marshal.WriteInt32(desc, 0, 136);
            Marshal.WriteInt16(desc, 4, (short)type);
            Marshal.WriteInt16(desc, 8, (short)vendor);
            Marshal.WriteInt16(desc, 10, (short)product);
            Marshal.WriteInt16(desc, 12, (short)axes);
            Marshal.WriteInt16(desc, 14, (short)buttons);
            Marshal.WriteInt16(desc, 18, (short)hats);
            Marshal.WriteIntPtr(desc, 40, namePtr);
            return SDL_AttachVirtualJoystick(desc);
        }
        finally
        {
            Marshal.FreeHGlobal(desc);
            // SDL copies the name when the device is attached.
            Marshal.FreeCoTaskMem(namePtr);
        }
    }
}
