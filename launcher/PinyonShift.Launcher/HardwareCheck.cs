using System.Runtime.InteropServices;
using System.Text;

namespace PinyonShift.Launcher;

// What this PC has for the game (LOW_SPEC_BACKLOG LS-1.7): the Vulkan GPU the
// game would pick, its own memory, its Vulkan version, the CPU's cores and the
// display's refresh rate, and the in-game preset that suits them.
public sealed record GpuInfo(string Name, bool Discrete, ulong DeviceLocalBytes, uint ApiVersion, uint VendorId = 0)
{
    public string VulkanVersion => $"{ApiVersion >> 22}.{(ApiVersion >> 12) & 0x3FF}";
    public bool SupportsVulkan13 => (ApiVersion >> 22) > 1 || ((ApiVersion >> 22) == 1 && ((ApiVersion >> 12) & 0x3FF) >= 3);
}

public sealed record HardwareInfo(GpuInfo? Gpu, int LogicalProcessors, int PhysicalCores, int RefreshHz);

public sealed record Recommendation(string Preset, string Label, string Reason, string? Warning);

public static class HardwareCheck
{
    public static HardwareInfo Probe(int refreshHz)
    {
        GpuInfo? gpu = null;
        try { gpu = ProbeVulkan(); }
        catch (Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException or SEHException) { }
        return new HardwareInfo(gpu, Environment.ProcessorCount, PhysicalCoreCount(), refreshHz);
    }

    // The rule the game applies to a new config (src/pinyon_shift_app.cpp,
    // ApplyFirstRunHardwareDefaults), plus Balanced 40 under 4 cores: the
    // simulated runs put 2 cores with 4 threads at the edge of 60 fps.
    public const ulong CapableDeviceLocalBytes = 6UL << 30;
    public const int CapableLogicalProcessors = 6;
    public const int CapableRefreshHz = 119;
    public const int SteadySixtyCores = 4;

    public static Recommendation Recommend(HardwareInfo info)
    {
        string? warning = info.Gpu switch
        {
            null => "No Vulkan GPU was found. Install the graphics driver from AMD, Intel or NVIDIA.",
            { SupportsVulkan13: false } gpu =>
                $"The game needs Vulkan 1.3; this driver offers {gpu.VulkanVersion}. Update the graphics driver.",
            _ => null
        };
        if (info.Gpu is { Discrete: true } discrete && discrete.DeviceLocalBytes >= CapableDeviceLocalBytes &&
            info.LogicalProcessors >= CapableLogicalProcessors && info.RefreshHz >= CapableRefreshHz)
        {
            return new Recommendation("performance_120", "Performance 120",
                "A discrete GPU with 6 GB or more, 6 or more CPU threads and a 120 Hz display.", warning);
        }
        if (info.PhysicalCores > 0 && info.PhysicalCores < SteadySixtyCores)
        {
            return new Recommendation("balanced_40", "Balanced 40",
                $"{info.PhysicalCores} CPU cores: 60 fps is at the edge below 4 cores, 40 fps is steady.", warning);
        }
        var reason = info.Gpu is { Discrete: false }
            ? "Integrated graphics: the cheapest image at 60 fps."
            : "The cheapest image at 60 fps: 1x, no MSAA, bilinear output.";
        return new Recommendation("low_spec_60", "Low-spec 60", reason, warning);
    }

    public static string Describe(HardwareInfo info)
    {
        var text = new StringBuilder();
        if (info.Gpu is { } gpu)
        {
            text.Append($"{gpu.Name} · {FormatBytes(gpu.DeviceLocalBytes)} {(gpu.Discrete ? "VRAM" : "shared memory")}" +
                        $" · Vulkan {gpu.VulkanVersion}");
        }
        else
        {
            text.Append("No Vulkan GPU found");
        }
        text.Append(info.PhysicalCores > 0
            ? $" · {info.PhysicalCores} cores, {info.LogicalProcessors} threads"
            : $" · {info.LogicalProcessors} threads");
        if (info.RefreshHz > 0) text.Append($" · {info.RefreshHz} Hz");
        return text.ToString();
    }

    private static string FormatBytes(ulong bytes) =>
        bytes >= 1UL << 30 ? $"{bytes / (double)(1UL << 30):0.#} GB" : $"{bytes >> 20} MB";

    // The vendor's driver download page for the GPU, or the troubleshooting
    // page when no Vulkan GPU answered.
    public static string DriverPage(GpuInfo? gpu) => gpu?.VendorId switch
    {
        0x1002 => "https://www.amd.com/en/support/download/drivers.html",
        0x10DE => "https://www.nvidia.com/en-us/drivers/",
        0x8086 => "https://www.intel.com/content/www/us/en/download-center/home.html",
        _ => "https://github.com/arcanite24/pinyon-shift/blob/main/docs/TROUBLESHOOTING.md"
    };

    // ---- Vulkan ------------------------------------------------------------

    private const int VkStructureTypeApplicationInfo = 0;
    private const int VkStructureTypeInstanceCreateInfo = 1;
    private const int VkPhysicalDeviceTypeIntegrated = 1;
    private const int VkPhysicalDeviceTypeDiscrete = 2;
    private const uint VkMemoryHeapDeviceLocal = 1;

    [StructLayout(LayoutKind.Sequential)]
    private struct VkApplicationInfo
    {
        public int sType;
        public IntPtr pNext;
        public IntPtr pApplicationName;
        public uint applicationVersion;
        public IntPtr pEngineName;
        public uint engineVersion;
        public uint apiVersion;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct VkInstanceCreateInfo
    {
        public int sType;
        public IntPtr pNext;
        public uint flags;
        public IntPtr pApplicationInfo;
        public uint enabledLayerCount;
        public IntPtr ppEnabledLayerNames;
        public uint enabledExtensionCount;
        public IntPtr ppEnabledExtensionNames;
    }

    [DllImport("vulkan-1.dll")]
    private static extern int vkCreateInstance(ref VkInstanceCreateInfo createInfo, IntPtr allocator, out IntPtr instance);

    [DllImport("vulkan-1.dll")]
    private static extern void vkDestroyInstance(IntPtr instance, IntPtr allocator);

    [DllImport("vulkan-1.dll")]
    private static extern int vkEnumeratePhysicalDevices(IntPtr instance, ref uint count, IntPtr[]? devices);

    // VkPhysicalDeviceProperties (824 bytes on x64) and
    // VkPhysicalDeviceMemoryProperties (520 bytes) as raw buffers: only a few
    // leading fields are read, at their fixed offsets.
    [DllImport("vulkan-1.dll")]
    private static extern void vkGetPhysicalDeviceProperties(IntPtr device, byte[] properties);

    [DllImport("vulkan-1.dll")]
    private static extern void vkGetPhysicalDeviceMemoryProperties(IntPtr device, byte[] properties);

    private static GpuInfo? ProbeVulkan()
    {
        var name = Marshal.StringToHGlobalAnsi("Pinyon Shift Launcher");
        var application = Marshal.AllocHGlobal(Marshal.SizeOf<VkApplicationInfo>());
        try
        {
            Marshal.StructureToPtr(new VkApplicationInfo
            {
                sType = VkStructureTypeApplicationInfo,
                pApplicationName = name,
                apiVersion = 1u << 22 | 1u << 12  // 1.1
            }, application, false);
            var create = new VkInstanceCreateInfo
            {
                sType = VkStructureTypeInstanceCreateInfo,
                pApplicationInfo = application
            };
            if (vkCreateInstance(ref create, IntPtr.Zero, out var instance) != 0) return null;
            try
            {
                uint count = 0;
                if (vkEnumeratePhysicalDevices(instance, ref count, null) != 0 || count == 0) return null;
                var devices = new IntPtr[count];
                if (vkEnumeratePhysicalDevices(instance, ref count, devices) < 0) return null;
                GpuInfo? best = null;
                foreach (var device in devices.Take((int)count))
                {
                    var gpu = DescribeDevice(device);
                    // A discrete GPU first, then the one with the most memory.
                    if (best is null || (gpu.Discrete && !best.Discrete) ||
                        (gpu.Discrete == best.Discrete && gpu.DeviceLocalBytes > best.DeviceLocalBytes))
                    {
                        best = gpu;
                    }
                }
                return best;
            }
            finally
            {
                vkDestroyInstance(instance, IntPtr.Zero);
            }
        }
        finally
        {
            Marshal.FreeHGlobal(application);
            Marshal.FreeHGlobal(name);
        }
    }

    private static GpuInfo DescribeDevice(IntPtr device)
    {
        var properties = new byte[1024];
        vkGetPhysicalDeviceProperties(device, properties);
        var apiVersion = BitConverter.ToUInt32(properties, 0);
        var deviceType = BitConverter.ToInt32(properties, 16);
        var nameBytes = properties.AsSpan(20, 256);
        var length = nameBytes.IndexOf((byte)0);
        var deviceName = Encoding.UTF8.GetString(length < 0 ? nameBytes : nameBytes[..length]);

        var memory = new byte[1024];
        vkGetPhysicalDeviceMemoryProperties(device, memory);
        var heapCount = Math.Min(BitConverter.ToUInt32(memory, 260), 16u);
        ulong deviceLocal = 0;
        for (var heap = 0; heap < heapCount; heap++)
        {
            var size = BitConverter.ToUInt64(memory, 264 + heap * 16);
            var flags = BitConverter.ToUInt32(memory, 272 + heap * 16);
            if ((flags & VkMemoryHeapDeviceLocal) != 0) deviceLocal = Math.Max(deviceLocal, size);
        }
        return new GpuInfo(deviceName, deviceType == VkPhysicalDeviceTypeDiscrete, deviceLocal, apiVersion,
            BitConverter.ToUInt32(properties, 8));
    }

    // ---- CPU ---------------------------------------------------------------

    private const int RelationProcessorCore = 0;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetLogicalProcessorInformationEx(int relationship, IntPtr buffer, ref uint length);

    // Physical cores (one SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX entry each),
    // or 0 when Windows does not say.
    private static int PhysicalCoreCount()
    {
        uint length = 0;
        GetLogicalProcessorInformationEx(RelationProcessorCore, IntPtr.Zero, ref length);
        if (length == 0) return 0;
        var buffer = Marshal.AllocHGlobal((int)length);
        try
        {
            if (!GetLogicalProcessorInformationEx(RelationProcessorCore, buffer, ref length)) return 0;
            var cores = 0;
            for (uint offset = 0; offset < length;)
            {
                var size = (uint)Marshal.ReadInt32(buffer, (int)offset + 4);
                if (size == 0) break;
                cores++;
                offset += size;
            }
            return cores;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }
}
