#!/usr/bin/env python3
"""What this computer has for the game, for the Desktop launcher's Settings
(LOW_SPEC_BACKLOG LS-1.7): launcher/PinyonShift.Launcher/HardwareCheck.cs on
every OS.

  pinyon.py hardware [--refresh-hz N] [--json]

It loads the Vulkan loader (libvulkan.so.1 on Linux, vulkan-1.dll on
Windows; on macOS the MoltenVK the build ships in rexglue-artifacts, or a
system libvulkan.1.dylib), picks the GPU the game would (a discrete one
first, then the one with the most memory), and reads its name, memory and
Vulkan version, the CPU's cores and threads and, where it is cheap, the
display's refresh rate. It recommends the in-game preset the game's own
first-run rule picks (ApplyFirstRunHardwareDefaults) and prints one object:

  {"result": "ok", "vulkan": {"loader", "available"}, "gpu": {"name",
   "discrete", "device_local_bytes", "api_version", "vulkan_version",
   "supports_vulkan_13", "vendor_id"} or null, "logical_processors",
   "physical_cores", "refresh_hz", "recommendation": {"preset", "label",
   "reason", "warning"}, "description", "driver_page"}
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402

# HardwareCheck.cs; tools/tests/test_hardware_check.py keeps them equal.
CAPABLE_DEVICE_LOCAL_BYTES = 6 << 30
CAPABLE_LOGICAL_PROCESSORS = 6
CAPABLE_REFRESH_HZ = 119
STEADY_SIXTY_CORES = 4
ULTRA_LOW_CORES = 2

VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU = 2
VK_PHYSICAL_DEVICE_TYPE_CPU = 4
VK_MEMORY_HEAP_DEVICE_LOCAL_BIT = 1
VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR = 1
# The version the probe asks for. MoltenVK reports a device's version as at
# most the one the application asked for, so asking for 1.1 read as "1.1".
VULKAN_13 = (1 << 22) | (3 << 12)


class ApplicationInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_int32), ("pNext", ctypes.c_void_p),
                ("pApplicationName", ctypes.c_char_p), ("applicationVersion", ctypes.c_uint32),
                ("pEngineName", ctypes.c_char_p), ("engineVersion", ctypes.c_uint32),
                ("apiVersion", ctypes.c_uint32)]


class InstanceCreateInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_int32), ("pNext", ctypes.c_void_p),
                ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.POINTER(ApplicationInfo)),
                ("enabledLayerCount", ctypes.c_uint32),
                ("ppEnabledLayerNames", ctypes.POINTER(ctypes.c_char_p)),
                ("enabledExtensionCount", ctypes.c_uint32),
                ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p))]


def loader_candidates() -> list[str]:
    if common.WINDOWS:
        return ["vulkan-1.dll"]
    if common.MACOS:
        found = []
        for build in (common.build_directory(), common.build_directory(v4=True)):
            artifacts = build / "rexglue-artifacts"
            found += [str(artifacts / name) for name in ("libMoltenVK.dylib", "libMoltenVK.1.dylib")
                      if (artifacts / name).is_file()]
        return found + ["libvulkan.1.dylib", "/usr/local/lib/libvulkan.1.dylib",
                        "/opt/homebrew/lib/libvulkan.1.dylib", "libMoltenVK.dylib"]
    return ["libvulkan.so.1", "libvulkan.so"]


def load_loader() -> tuple[ctypes.CDLL | None, str | None]:
    # MoltenVK logs its whole extension list to stderr at every instance.
    os.environ.setdefault("MVK_CONFIG_LOG_LEVEL", "0")
    for name in loader_candidates():
        try:
            return ctypes.CDLL(name), name
        except OSError:
            continue
    return None, None


def describe_device(vulkan, device) -> dict:
    properties = ctypes.create_string_buffer(1024)
    vulkan.vkGetPhysicalDeviceProperties(device, properties)
    raw = properties.raw
    api_version = int.from_bytes(raw[0:4], "little")
    vendor_id = int.from_bytes(raw[8:12], "little")
    device_type = int.from_bytes(raw[16:20], "little")
    name = raw[20:276].split(b"\0", 1)[0].decode("utf-8", "replace")
    memory = ctypes.create_string_buffer(1024)
    vulkan.vkGetPhysicalDeviceMemoryProperties(device, memory)
    raw = memory.raw
    heaps = min(int.from_bytes(raw[260:264], "little"), 16)
    device_local = 0
    for heap in range(heaps):
        size = int.from_bytes(raw[264 + heap * 16:272 + heap * 16], "little")
        flags = int.from_bytes(raw[272 + heap * 16:276 + heap * 16], "little")
        if flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT:
            device_local = max(device_local, size)
    return gpu_record(name, device_type == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU, device_local,
                      api_version, vendor_id, device_type == VK_PHYSICAL_DEVICE_TYPE_CPU)


def gpu_record(name: str, discrete: bool, device_local: int, api_version: int,
               vendor_id: int = 0, software: bool = False) -> dict:
    major, minor = api_version >> 22, (api_version >> 12) & 0x3FF
    return {"name": name, "discrete": discrete, "device_local_bytes": device_local,
            "api_version": api_version, "vulkan_version": f"{major}.{minor}",
            "supports_vulkan_13": major > 1 or (major == 1 and minor >= 3),
            "vendor_id": vendor_id, "software": software}


def probe_vulkan(vulkan, direct_icd: bool = False) -> dict | None:
    """direct_icd: the library is MoltenVK itself, not a loader in front of it."""
    vulkan.vkCreateInstance.restype = ctypes.c_int32
    vulkan.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
    vulkan.vkGetPhysicalDeviceProperties.restype = None
    vulkan.vkGetPhysicalDeviceMemoryProperties.restype = None
    vulkan.vkDestroyInstance.restype = None
    application = ApplicationInfo(VK_STRUCTURE_TYPE_APPLICATION_INFO, None,
                                  b"Pinyon Shift Launcher", 0, None, 0, VULKAN_13)
    attempts = [(0, [])]
    if common.MACOS and not direct_icd:
        # A loader in front of MoltenVK lists it only with portability enumeration.
        attempts.insert(0, (VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR,
                            [b"VK_KHR_portability_enumeration"]))
    instance = ctypes.c_void_p()
    for flags, extensions in attempts:
        names = (ctypes.c_char_p * max(1, len(extensions)))(*extensions)
        create = InstanceCreateInfo(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, None, flags,
                                    ctypes.pointer(application), 0, None, len(extensions),
                                    names if extensions else None)
        if vulkan.vkCreateInstance(ctypes.byref(create), None, ctypes.byref(instance)) == 0:
            break
        instance = ctypes.c_void_p()
    if not instance.value:
        return None
    try:
        count = ctypes.c_uint32(0)
        if vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None) != 0 or \
                count.value == 0:
            return None
        devices = (ctypes.c_void_p * count.value)()
        if vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices) < 0:
            return None
        best = None
        for device in devices[:count.value]:
            gpu = describe_device(vulkan, ctypes.c_void_p(device))
            # A GPU before a software renderer (llvmpipe, whose memory is
            # the system's), a discrete GPU first, then the most memory.
            rank = (not gpu["software"], gpu["discrete"], gpu["device_local_bytes"])
            if best is None or rank > (not best["software"], best["discrete"],
                                       best["device_local_bytes"]):
                best = gpu
        return best
    finally:
        vulkan.vkDestroyInstance(instance, None)


def physical_cores() -> int:
    """Physical cores, or 0 when the OS does not say."""
    try:
        if common.WINDOWS:
            return _windows_cores()
        if common.MACOS:
            out = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True,
                                 text=True).stdout.strip()
            return int(out) if out.isdigit() else 0
        cores, physical = set(), "0"
        for line in Path("/proc/cpuinfo").read_text(encoding="ascii", errors="replace").splitlines():
            key, _, value = line.partition(":")
            key = key.strip()
            if key == "physical id":
                physical = value.strip()
            elif key == "core id":
                cores.add((physical, value.strip()))
        return len(cores)
    except (OSError, ValueError):
        return 0


def _windows_cores() -> int:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    length = ctypes.c_uint32(0)
    kernel.GetLogicalProcessorInformationEx(0, None, ctypes.byref(length))
    if not length.value:
        return 0
    buffer = ctypes.create_string_buffer(length.value)
    if not kernel.GetLogicalProcessorInformationEx(0, buffer, ctypes.byref(length)):
        return 0
    cores, offset, raw = 0, 0, buffer.raw
    while offset < length.value:
        size = int.from_bytes(raw[offset + 4:offset + 8], "little")
        if size == 0:
            break
        cores += 1
        offset += size
    return cores


def refresh_rate() -> int:
    """The primary display's refresh rate where it is cheap to read, else 0."""
    try:
        if common.WINDOWS:
            mode = ctypes.create_string_buffer(220)
            mode[68:70] = (220).to_bytes(2, "little")  # dmSize
            if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, mode):
                return int.from_bytes(mode.raw[184:188], "little")
            return 0
        if sys.platform.startswith("linux") and shutil.which("xrandr") and \
                os.environ.get("DISPLAY"):
            out = subprocess.run(["xrandr", "--current"], capture_output=True, text=True,
                                 timeout=5).stdout
            rates = [float(rate) for rate in re.findall(r"(\d+(?:\.\d+)?)\*", out)]
            return int(round(max(rates))) if rates else 0
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        pass
    return 0


def recommend(gpu: dict | None, logical: int, cores: int, refresh: int) -> dict:
    if gpu is None:
        if common.MACOS:
            warning = ("No Vulkan GPU answered. MoltenVK comes with the build: build the game "
                       "first, then check again.")
        elif common.WINDOWS:
            warning = "No Vulkan GPU was found. Install the graphics driver from AMD, Intel or NVIDIA."
        else:
            warning = ("No Vulkan GPU was found. Install your distribution's Vulkan driver "
                       "(Mesa's RADV or ANV, or NVIDIA's driver) and the Vulkan loader "
                       "(libvulkan1 or vulkan-loader).")
    elif gpu.get("software"):
        warning = (f"Only a software Vulkan renderer answered ({gpu['name']}); the game would "
                   "draw on the CPU, far too slowly to play. Install the GPU's Vulkan driver.")
    elif not gpu["supports_vulkan_13"]:
        warning = (f"The game needs Vulkan 1.3; this driver offers {gpu['vulkan_version']}. "
                   "Update the graphics driver.")
    else:
        warning = None
    if gpu and gpu["discrete"] and gpu["device_local_bytes"] >= CAPABLE_DEVICE_LOCAL_BYTES and \
            logical >= CAPABLE_LOGICAL_PROCESSORS and refresh >= CAPABLE_REFRESH_HZ:
        return {"preset": "performance_120", "label": "Performance 120",
                "reason": "A discrete GPU with 6 GB or more, 6 or more CPU threads and a 120 Hz "
                          "display.", "warning": warning}
    # Ultra Low 30 (#515): integrated graphics on 2 CPU cores.
    if gpu and not gpu["discrete"] and 0 < cores <= ULTRA_LOW_CORES:
        return {"preset": "ultra_low_30", "label": "Ultra Low 30",
                "reason": f"Integrated graphics and {cores} CPU cores: 30 fps without shadows.",
                "warning": warning}
    if 0 < cores < STEADY_SIXTY_CORES:
        return {"preset": "balanced_40", "label": "Balanced 40",
                "reason": f"{cores} CPU cores: 60 fps is at the edge below 4 cores, 40 fps is "
                          "steady.", "warning": warning}
    reason = ("Integrated graphics: the cheapest image at 60 fps." if gpu and not gpu["discrete"]
              else "The cheapest image at 60 fps: 1x, no MSAA, bilinear output.")
    return {"preset": "low_spec_60", "label": "Low-spec 60", "reason": reason, "warning": warning}


def format_bytes(value: int) -> str:
    if value >= 1 << 30:
        return f"{value / (1 << 30):.1f}".rstrip("0").rstrip(".") + " GB"
    return f"{value >> 20} MB"


def describe(gpu: dict | None, logical: int, cores: int, refresh: int) -> str:
    if gpu:
        text = (f"{gpu['name']} · {format_bytes(gpu['device_local_bytes'])} "
                f"{'VRAM' if gpu['discrete'] else 'shared memory'} · Vulkan {gpu['vulkan_version']}")
    else:
        text = "No Vulkan GPU found"
    text += f" · {cores} cores, {logical} threads" if cores > 0 else f" · {logical} threads"
    if refresh > 0:
        text += f" · {refresh} Hz"
    return text


def driver_page(gpu: dict | None) -> str:
    vendor = gpu["vendor_id"] if gpu else 0
    if not common.WINDOWS and vendor in (0x1002, 0x8086):
        # Mesa ships AMD's and Intel's Vulkan drivers on Linux.
        return "https://docs.mesa3d.org/download.html"
    return {0x1002: "https://www.amd.com/en/support/download/drivers.html",
            0x10DE: "https://www.nvidia.com/en-us/drivers/",
            0x8086: "https://www.intel.com/content/www/us/en/download-center/home.html"}.get(
        vendor, f"{common.REPOSITORY_URL}/blob/main/docs/TROUBLESHOOTING.md")


def run(args: argparse.Namespace) -> dict:
    vulkan, loader = load_loader()
    gpu = None
    if vulkan is not None:
        try:
            gpu = probe_vulkan(vulkan, Path(loader).name.startswith("libMoltenVK"))
        except (OSError, AttributeError, ValueError):
            gpu = None
    logical = os.cpu_count() or 0
    cores = physical_cores()
    refresh = args.refresh_hz if args.refresh_hz is not None else refresh_rate()
    return {"vulkan": {"loader": loader, "available": gpu is not None}, "gpu": gpu,
            "logical_processors": logical, "physical_cores": cores, "refresh_hz": refresh,
            "recommendation": recommend(gpu, logical, cores, refresh),
            "description": describe(gpu, logical, cores, refresh), "driver_page": driver_page(gpu)}


def add_parser(commands) -> None:
    parser = commands.add_parser("hardware", help="the GPU, CPU and display, and a preset for them")
    parser.add_argument("--refresh-hz", type=int, help="the display's refresh rate, when known")
    parser.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
