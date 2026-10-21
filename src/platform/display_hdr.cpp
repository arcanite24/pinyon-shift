#include "platform/display_hdr.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <optional>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>
#endif

namespace pinyon_shift::platform {

const char* DisplayHdrResultName(DisplayHdrResult result) {
  switch (result) {
    case DisplayHdrResult::kTurnedOn:
      return "turned_on";
    case DisplayHdrResult::kAlreadyOn:
      return "already_on";
    case DisplayHdrResult::kUnsupported:
      return "unsupported";
    case DisplayHdrResult::kFailed:
      return "failed";
  }
  return "unknown";
}

#if defined(_WIN32)
namespace {

// The display configuration requests, declared here so the build does not
// depend on the Windows SDK having the 24H2 ones (types 15 and 16). Layouts
// follow wingdi.h; each request starts with DISPLAYCONFIG_DEVICE_INFO_HEADER.
constexpr uint32_t kGetAdvancedColorInfo = 9;
constexpr uint32_t kSetAdvancedColorState = 10;
constexpr uint32_t kGetAdvancedColorInfo2 = 15;
constexpr uint32_t kSetHdrState = 16;

struct AdvancedColorInfo {
  DISPLAYCONFIG_DEVICE_INFO_HEADER header;
  uint32_t flags;  // supported 0x1, enabled 0x2, wide color enforced 0x4, force
                   // disabled 0x8
  uint32_t color_encoding;
  uint32_t bits_per_color_channel;
};

// Windows 11 24H2 split HDR from advanced color (which SDR displays also get
// for color management), so "enabled" there no longer means HDR.
struct AdvancedColorInfo2 {
  DISPLAYCONFIG_DEVICE_INFO_HEADER header;
  uint32_t flags;  // HDR supported 0x10, HDR user enabled 0x20
  uint32_t color_encoding;
  uint32_t bits_per_color_channel;
  uint32_t active_color_mode;
};

struct SetState {
  DISPLAYCONFIG_DEVICE_INFO_HEADER header;
  uint32_t value;  // bit 0: on
};

constexpr uint32_t kAdvancedColorSupported = 0x1;
constexpr uint32_t kAdvancedColorEnabled = 0x2;
constexpr uint32_t kAdvancedColorForceDisabled = 0x8;
constexpr uint32_t kHdrSupported = 0x10;
constexpr uint32_t kHdrUserEnabled = 0x20;

struct Target {
  LUID adapter{};
  uint32_t id = 0;
  bool operator==(const Target& other) const {
    return adapter.LowPart == other.adapter.LowPart && adapter.HighPart == other.adapter.HighPart &&
           id == other.id;
  }
};

std::mutex g_mutex;
std::vector<Target> g_owned;
std::filesystem::path g_restore_file;

template <typename Request>
Request MakeRequest(uint32_t type, const Target& target) {
  Request request{};
  request.header.type = static_cast<DISPLAYCONFIG_DEVICE_INFO_TYPE>(type);
  request.header.size = sizeof(Request);
  request.header.adapterId = target.adapter;
  request.header.id = target.id;
  return request;
}

// Whether HDR is on, or nothing when the display cannot do HDR.
std::optional<bool> HdrOn(const Target& target, bool& has_hdr_state) {
  auto info2 = MakeRequest<AdvancedColorInfo2>(kGetAdvancedColorInfo2, target);
  if (DisplayConfigGetDeviceInfo(&info2.header) == ERROR_SUCCESS) {
    has_hdr_state = true;
    if (!(info2.flags & kHdrSupported))
      return std::nullopt;
    return (info2.flags & kHdrUserEnabled) != 0;
  }
  has_hdr_state = false;
  auto info = MakeRequest<AdvancedColorInfo>(kGetAdvancedColorInfo, target);
  if (DisplayConfigGetDeviceInfo(&info.header) != ERROR_SUCCESS ||
      !(info.flags & kAdvancedColorSupported) || (info.flags & kAdvancedColorForceDisabled)) {
    return std::nullopt;
  }
  return (info.flags & kAdvancedColorEnabled) != 0;
}

bool SetHdr(const Target& target, bool on, bool has_hdr_state) {
  auto request =
      MakeRequest<SetState>(has_hdr_state ? kSetHdrState : kSetAdvancedColorState, target);
  request.value = on ? 1 : 0;
  return DisplayConfigSetDeviceInfo(&request.header) == ERROR_SUCCESS;
}

// The targets (more than one when cloned) showing the GDI display `device`.
std::vector<Target> TargetsOf(const wchar_t* device) {
  std::vector<Target> targets;
  for (int attempt = 0; attempt < 3; ++attempt) {
    UINT32 path_count = 0, mode_count = 0;
    if (GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &path_count, &mode_count) !=
        ERROR_SUCCESS) {
      return targets;
    }
    std::vector<DISPLAYCONFIG_PATH_INFO> paths(path_count);
    std::vector<DISPLAYCONFIG_MODE_INFO> modes(mode_count);
    const LONG status = QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &path_count, paths.data(),
                                           &mode_count, modes.data(), nullptr);
    if (status == ERROR_INSUFFICIENT_BUFFER)
      continue;  // Changed in between.
    if (status != ERROR_SUCCESS)
      return targets;
    paths.resize(path_count);
    for (const DISPLAYCONFIG_PATH_INFO& path : paths) {
      DISPLAYCONFIG_SOURCE_DEVICE_NAME source{};
      source.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
      source.header.size = sizeof(source);
      source.header.adapterId = path.sourceInfo.adapterId;
      source.header.id = path.sourceInfo.id;
      if (DisplayConfigGetDeviceInfo(&source.header) == ERROR_SUCCESS &&
          _wcsicmp(source.viewGdiDeviceName, device) == 0) {
        targets.push_back({path.targetInfo.adapterId, path.targetInfo.id});
      }
    }
    return targets;
  }
  return targets;
}

// Lists the owned displays, or removes the file when there are none. Under
// g_mutex.
void WriteRestoreFile() {
  if (g_restore_file.empty())
    return;
  std::error_code error;
  if (g_owned.empty()) {
    std::filesystem::remove(g_restore_file, error);
    return;
  }
  std::ofstream file(g_restore_file, std::ios::trunc);
  for (const Target& target : g_owned) {
    file << target.adapter.HighPart << ' ' << target.adapter.LowPart << ' ' << target.id << '\n';
  }
}

DisplayHdrResult TurnOnMonitor(HMONITOR monitor) {
  MONITORINFOEXW info{};
  info.cbSize = sizeof(info);
  if (!monitor || !GetMonitorInfoW(monitor, &info))
    return DisplayHdrResult::kUnsupported;
  const std::vector<Target> targets = TargetsOf(info.szDevice);
  std::lock_guard lock(g_mutex);
  DisplayHdrResult result = DisplayHdrResult::kUnsupported;
  for (const Target& target : targets) {
    bool has_hdr_state = false;
    const std::optional<bool> on = HdrOn(target, has_hdr_state);
    if (!on)
      continue;
    if (*on) {
      if (result == DisplayHdrResult::kUnsupported)
        result = DisplayHdrResult::kAlreadyOn;
      continue;
    }
    if (!SetHdr(target, true, has_hdr_state)) {
      result = DisplayHdrResult::kFailed;
      continue;
    }
    if (std::find(g_owned.begin(), g_owned.end(), target) == g_owned.end()) {
      g_owned.push_back(target);
    }
    // The restore file first lists it, so even a crash right away is undone.
    WriteRestoreFile();
    if (result != DisplayHdrResult::kFailed)
      result = DisplayHdrResult::kTurnedOn;
  }
  return result;
}

}  // namespace

void SetDisplayHdrRestoreFile(std::filesystem::path path) {
  std::lock_guard lock(g_mutex);
  g_restore_file = std::move(path);
  std::ifstream file(g_restore_file);
  long high = 0;
  unsigned long low = 0;
  uint32_t id = 0;
  while (file >> high >> low >> id) {
    Target target;
    target.adapter.HighPart = high;
    target.adapter.LowPart = low;
    target.id = id;
    if (std::find(g_owned.begin(), g_owned.end(), target) == g_owned.end()) {
      g_owned.push_back(target);
    }
  }
}

DisplayHdrResult TurnOnDisplayHdr(void* native_window) {
  return TurnOnMonitor(
      MonitorFromWindow(static_cast<HWND>(native_window), MONITOR_DEFAULTTOPRIMARY));
}

DisplayHdrResult TurnOnDisplayHdrAt(int x, int y) {
  return TurnOnMonitor(MonitorFromPoint(POINT{x, y}, MONITOR_DEFAULTTOPRIMARY));
}

int RestoreDisplayHdr() {
  // A crash handler may run while the crashed thread holds the lock; go on
  // without it after a short wait rather than hang the exit.
  std::unique_lock lock(g_mutex, std::defer_lock);
  for (int attempt = 0; attempt < 50 && !lock.try_lock(); ++attempt) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  int restored = 0;
  for (const Target& target : g_owned) {
    bool has_hdr_state = false;
    // A display gone since (or with another LUID after a reboot) fails the
    // query and is skipped.
    if (HdrOn(target, has_hdr_state).value_or(false) && SetHdr(target, false, has_hdr_state)) {
      ++restored;
    }
  }
  g_owned.clear();
  WriteRestoreFile();
  return restored;
}

#else

void SetDisplayHdrRestoreFile(std::filesystem::path) {}
DisplayHdrResult TurnOnDisplayHdr(void*) {
  return DisplayHdrResult::kUnsupported;
}
DisplayHdrResult TurnOnDisplayHdrAt(int, int) {
  return DisplayHdrResult::kUnsupported;
}
int RestoreDisplayHdr() {
  return 0;
}

#endif

}  // namespace pinyon_shift::platform
