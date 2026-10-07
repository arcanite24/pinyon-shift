// VRAM balloon (LOW_SPEC_BACKLOG LS-0.5): holds device-local memory in a
// process of its own, so a game started beside it gets a smaller heap budget
// (VK_EXT_memory_budget) and runs as on a GPU with less memory.
//
//   pinyon_shift_vram_balloon <gigabytes> [--device N] [--seconds S]
//
// Allocates in 256 MiB blocks, writes each with vkCmdFillBuffer so it is
// resident, prints one JSON line with what it holds, and keeps the memory
// until stdin closes, the time runs out or it is killed. Sensitivity data
// only: the card keeps its bandwidth and the driver its behaviour.
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

PFN_vkGetInstanceProcAddr get_instance_proc = nullptr;

template <typename T>
T Instance(VkInstance instance, const char* name) {
  return reinterpret_cast<T>(get_instance_proc(instance, name));
}

int Fail(const char* what, VkResult result = VK_SUCCESS) {
  std::fprintf(stderr, "vram_balloon: %s (%d)\n", what, int(result));
  return 1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) {
    std::fprintf(stderr, "usage: %s <gigabytes> [--device N] [--seconds S]\n", argv[0]);
    return 2;
  }
  const double gigabytes = std::atof(argv[1]);
  uint32_t device_index = 0;
  double seconds = 0;
  for (int i = 2; i + 1 < argc; i += 2) {
    if (!std::strcmp(argv[i], "--device")) device_index = uint32_t(std::atoi(argv[i + 1]));
    if (!std::strcmp(argv[i], "--seconds")) seconds = std::atof(argv[i + 1]);
  }
  if (gigabytes <= 0) return Fail("size must be positive");

  HMODULE loader = LoadLibraryA("vulkan-1.dll");
  if (!loader) return Fail("vulkan-1.dll not found");
  get_instance_proc =
      reinterpret_cast<PFN_vkGetInstanceProcAddr>(GetProcAddress(loader, "vkGetInstanceProcAddr"));
  auto create_instance = Instance<PFN_vkCreateInstance>(nullptr, "vkCreateInstance");

  VkApplicationInfo app = {VK_STRUCTURE_TYPE_APPLICATION_INFO};
  app.pApplicationName = "pinyon_shift_vram_balloon";
  app.apiVersion = VK_API_VERSION_1_1;
  VkInstanceCreateInfo instance_info = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  instance_info.pApplicationInfo = &app;
  VkInstance instance = VK_NULL_HANDLE;
  if (VkResult result = create_instance(&instance_info, nullptr, &instance)) {
    return Fail("vkCreateInstance", result);
  }
  auto enumerate = Instance<PFN_vkEnumeratePhysicalDevices>(instance, "vkEnumeratePhysicalDevices");
  uint32_t count = 0;
  enumerate(instance, &count, nullptr);
  std::vector<VkPhysicalDevice> physical_devices(count);
  enumerate(instance, &count, physical_devices.data());
  if (device_index >= count) return Fail("no such device");
  const VkPhysicalDevice physical = physical_devices[device_index];

  VkPhysicalDeviceProperties properties = {};
  Instance<PFN_vkGetPhysicalDeviceProperties>(instance, "vkGetPhysicalDeviceProperties")(
      physical, &properties);
  VkPhysicalDeviceMemoryProperties memory = {};
  Instance<PFN_vkGetPhysicalDeviceMemoryProperties>(instance,
                                                    "vkGetPhysicalDeviceMemoryProperties")(
      physical, &memory);
  uint32_t memory_type = UINT32_MAX;
  for (uint32_t i = 0; i < memory.memoryTypeCount; ++i) {
    const VkMemoryType& type = memory.memoryTypes[i];
    // Device-local and not host-visible: VRAM proper, not the BAR window.
    if ((type.propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) &&
        !(type.propertyFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) {
      memory_type = i;
      break;
    }
  }
  if (memory_type == UINT32_MAX) return Fail("no device-local memory type");

  uint32_t family_count = 0;
  auto families =
      Instance<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(instance,
                                                            "vkGetPhysicalDeviceQueueFamilyProperties");
  families(physical, &family_count, nullptr);
  std::vector<VkQueueFamilyProperties> family_properties(family_count);
  families(physical, &family_count, family_properties.data());
  uint32_t family = UINT32_MAX;
  for (uint32_t i = 0; i < family_count; ++i) {
    if (family_properties[i].queueFlags & (VK_QUEUE_TRANSFER_BIT | VK_QUEUE_GRAPHICS_BIT)) {
      family = i;
      break;
    }
  }
  if (family == UINT32_MAX) return Fail("no transfer queue");

  const float priority = 1.0f;
  VkDeviceQueueCreateInfo queue_info = {VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
  queue_info.queueFamilyIndex = family;
  queue_info.queueCount = 1;
  queue_info.pQueuePriorities = &priority;
  VkDeviceCreateInfo device_info = {VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
  device_info.queueCreateInfoCount = 1;
  device_info.pQueueCreateInfos = &queue_info;
  VkDevice device = VK_NULL_HANDLE;
  if (VkResult result = Instance<PFN_vkCreateDevice>(instance, "vkCreateDevice")(
          physical, &device_info, nullptr, &device)) {
    return Fail("vkCreateDevice", result);
  }
  auto get_device_proc =
      Instance<PFN_vkGetDeviceProcAddr>(instance, "vkGetDeviceProcAddr");
#define DEVICE(name) auto name = reinterpret_cast<PFN_##name>(get_device_proc(device, #name))
  DEVICE(vkGetDeviceQueue);
  DEVICE(vkCreateBuffer);
  DEVICE(vkGetBufferMemoryRequirements);
  DEVICE(vkAllocateMemory);
  DEVICE(vkBindBufferMemory);
  DEVICE(vkCreateCommandPool);
  DEVICE(vkAllocateCommandBuffers);
  DEVICE(vkBeginCommandBuffer);
  DEVICE(vkCmdFillBuffer);
  DEVICE(vkEndCommandBuffer);
  DEVICE(vkQueueSubmit);
  DEVICE(vkQueueWaitIdle);
#undef DEVICE
  VkQueue queue = VK_NULL_HANDLE;
  vkGetDeviceQueue(device, family, 0, &queue);
  VkCommandPoolCreateInfo pool_info = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
  pool_info.queueFamilyIndex = family;
  VkCommandPool pool = VK_NULL_HANDLE;
  vkCreateCommandPool(device, &pool_info, nullptr, &pool);

  constexpr VkDeviceSize kBlock = VkDeviceSize(256) << 20;
  const VkDeviceSize target = VkDeviceSize(gigabytes * double(VkDeviceSize(1) << 30));
  VkDeviceSize held = 0;
  while (held < target) {
    VkBufferCreateInfo buffer_info = {VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    buffer_info.size = std::min(kBlock, target - held);
    buffer_info.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    VkBuffer buffer = VK_NULL_HANDLE;
    if (vkCreateBuffer(device, &buffer_info, nullptr, &buffer)) break;
    VkMemoryRequirements requirements = {};
    vkGetBufferMemoryRequirements(device, buffer, &requirements);
    VkMemoryAllocateInfo allocate_info = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    allocate_info.allocationSize = requirements.size;
    allocate_info.memoryTypeIndex = memory_type;
    VkDeviceMemory block = VK_NULL_HANDLE;
    if (vkAllocateMemory(device, &allocate_info, nullptr, &block)) break;
    vkBindBufferMemory(device, buffer, block, 0);
    // Write the block so the allocation is resident, not just reserved.
    VkCommandBufferAllocateInfo command_info = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    command_info.commandPool = pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = 1;
    VkCommandBuffer command = VK_NULL_HANDLE;
    vkAllocateCommandBuffers(device, &command_info, &command);
    VkCommandBufferBeginInfo begin = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    vkBeginCommandBuffer(command, &begin);
    vkCmdFillBuffer(command, buffer, 0, VK_WHOLE_SIZE, 0x5A5A5A5Au);
    vkEndCommandBuffer(command);
    VkSubmitInfo submit = {VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &command;
    vkQueueSubmit(queue, 1, &submit, VK_NULL_HANDLE);
    vkQueueWaitIdle(queue);
    held += buffer_info.size;
  }
  std::printf("{\"device\":\"%s\",\"requested_mb\":%llu,\"held_mb\":%llu}\n",
              properties.deviceName, (unsigned long long)(target >> 20),
              (unsigned long long)(held >> 20));
  std::fflush(stdout);
  if (held < target) {
    std::fprintf(stderr, "vram_balloon: holding only %llu MB\n", (unsigned long long)(held >> 20));
  }

  // Hold until stdin closes (the runner ends the balloon by closing it), the
  // time runs out, or the process is killed. Exit frees everything.
  const auto start = std::chrono::steady_clock::now();
  HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
  const bool pipe = input && GetFileType(input) == FILE_TYPE_PIPE;
  for (;;) {
    if (seconds > 0 &&
        std::chrono::steady_clock::now() - start >= std::chrono::duration<double>(seconds)) {
      break;
    }
    if (pipe) {
      DWORD available = 0;
      if (!PeekNamedPipe(input, nullptr, 0, nullptr, &available, nullptr)) break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }
  return 0;
}
