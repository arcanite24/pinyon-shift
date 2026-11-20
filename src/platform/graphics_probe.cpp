#include "platform/graphics_probe.h"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include <vector>

namespace pinyon_shift::platform {

#if defined(_WIN32)
namespace {

// Just the Vulkan entry points and structures the probe needs, so this file
// does not depend on the SDK's Vulkan headers or link the loader.
using VkInstance = struct VkInstance_T*;
using VkPhysicalDevice = struct VkPhysicalDevice_T*;
using VkResult = int32_t;

struct VkApplicationInfo {
  int32_t sType;  // VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
  const void* pNext;
  const char* pApplicationName;
  uint32_t applicationVersion;
  const char* pEngineName;
  uint32_t engineVersion;
  uint32_t apiVersion;
};

struct VkInstanceCreateInfo {
  int32_t sType;  // VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
  const void* pNext;
  uint32_t flags;
  const VkApplicationInfo* pApplicationInfo;
  uint32_t enabledLayerCount;
  const char* const* ppEnabledLayerNames;
  uint32_t enabledExtensionCount;
  const char* const* ppEnabledExtensionNames;
};

// VkPhysicalDeviceProperties begins with apiVersion; the rest of the
// structure (under 1 KB) is not read.
struct VkPhysicalDevicePropertiesPrefix {
  uint32_t apiVersion;
  uint8_t rest[1020];
};

using PFN_vkCreateInstance = VkResult(__stdcall*)(const VkInstanceCreateInfo*, const void*,
                                                  VkInstance*);
using PFN_vkDestroyInstance = void(__stdcall*)(VkInstance, const void*);
using PFN_vkEnumeratePhysicalDevices = VkResult(__stdcall*)(VkInstance, uint32_t*,
                                                            VkPhysicalDevice*);
using PFN_vkGetPhysicalDeviceProperties = void(__stdcall*)(VkPhysicalDevice,
                                                           VkPhysicalDevicePropertiesPrefix*);
using PFN_vkGetInstanceProcAddr = void*(__stdcall*)(VkInstance, const char*);

}  // namespace

uint32_t BestVulkanDeviceApiVersion() {
  HMODULE loader = LoadLibraryW(L"vulkan-1.dll");
  if (!loader) return 0;
  uint32_t best = 0;
  auto get_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
      GetProcAddress(loader, "vkGetInstanceProcAddr"));
  auto create = get_proc ? reinterpret_cast<PFN_vkCreateInstance>(
                               get_proc(nullptr, "vkCreateInstance"))
                         : nullptr;
  if (create) {
    // Vulkan 1.0 instance: a 1.0-only loader rejects a higher version, and
    // each device still reports its own version.
    VkApplicationInfo app = {0, nullptr, "Pinyon Shift probe", 0, nullptr, 0, 1u << 22};
    VkInstanceCreateInfo info = {1, nullptr, 0, &app, 0, nullptr, 0, nullptr};
    VkInstance instance = nullptr;
    if (create(&info, nullptr, &instance) == 0 && instance) {
      auto destroy = reinterpret_cast<PFN_vkDestroyInstance>(
          get_proc(instance, "vkDestroyInstance"));
      auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(
          get_proc(instance, "vkEnumeratePhysicalDevices"));
      auto properties = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(
          get_proc(instance, "vkGetPhysicalDeviceProperties"));
      uint32_t count = 0;
      if (enumerate && properties && enumerate(instance, &count, nullptr) >= 0 && count) {
        std::vector<VkPhysicalDevice> devices(count);
        if (enumerate(instance, &count, devices.data()) >= 0) {
          for (uint32_t i = 0; i < count; ++i) {
            VkPhysicalDevicePropertiesPrefix props = {};
            properties(devices[i], &props);
            if (props.apiVersion > best) best = props.apiVersion;
          }
        }
      }
      if (destroy) destroy(instance, nullptr);
    }
  }
  FreeLibrary(loader);
  return best;
}

bool HasDirect3D11FeatureLevel11() {
  HMODULE d3d11 = LoadLibraryW(L"d3d11.dll");
  if (!d3d11) return false;
  // D3D11CreateDevice with no output pointers only reports whether the
  // device could be made (S_FALSE).
  using PFN_D3D11CreateDevice =
      HRESULT(WINAPI*)(void*, int, HMODULE, UINT, const int*, UINT, UINT, void**, int*, void**);
  auto create =
      reinterpret_cast<PFN_D3D11CreateDevice>(GetProcAddress(d3d11, "D3D11CreateDevice"));
  bool supported = false;
  if (create) {
    const int feature_level_11_0 = 0xB000;  // D3D_FEATURE_LEVEL_11_0
    const int driver_type_hardware = 1;     // D3D_DRIVER_TYPE_HARDWARE
    const UINT sdk_version = 7;             // D3D11_SDK_VERSION
    supported = SUCCEEDED(create(nullptr, driver_type_hardware, nullptr, 0, &feature_level_11_0,
                                 1, sdk_version, nullptr, nullptr, nullptr));
  }
  FreeLibrary(d3d11);
  return supported;
}
#else
uint32_t BestVulkanDeviceApiVersion() { return 0; }
bool HasDirect3D11FeatureLevel11() { return false; }
#endif

}  // namespace pinyon_shift::platform
