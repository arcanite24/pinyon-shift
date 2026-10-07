#include "mod/overlay_device.h"

#include <mutex>
#include <set>

#include <rex/filesystem/entry.h>
#include <rex/logging.h>

#include "pinyon_shift_diagnostics.h"

namespace pinyon_shift::mod {

OverlayDevice::OverlayDevice(std::string_view mount_path, const std::filesystem::path& base_root,
                             std::vector<std::filesystem::path> overlay_roots)
    : Device(mount_path) {
  // Game files are read-only, the base and every overlay alike.
  base_ = std::make_unique<rex::filesystem::HostPathDevice>(mount_path, base_root, true);
  for (const auto& root : overlay_roots) {
    overlays_.push_back(
        std::make_unique<rex::filesystem::HostPathDevice>(mount_path, root, true));
  }
}

bool OverlayDevice::Initialize() {
  if (!base_->Initialize()) {
    return false;
  }
  for (auto it = overlays_.begin(); it != overlays_.end();) {
    if ((*it)->Initialize()) {
      ++it;
    } else {
      REXLOG_WARN("Mods: cannot read {}; its files are not used", (*it)->host_path().string());
      it = overlays_.erase(it);
    }
  }
  return true;
}

void OverlayDevice::Dump(rex::string::StringBuffer* string_buffer) {
  base_->Dump(string_buffer);
}

namespace {

std::mutex g_overridden_mutex;
std::set<std::string, std::less<>> g_overridden;

// "\media\db\gamedb.slt" for "game:\media\DB\gamedb.slt" or "media/db/gamedb.slt".
std::string NormalizeGamePath(std::string_view path) {
  if (const size_t colon = path.find(':'); colon != std::string_view::npos) {
    path.remove_prefix(colon + 1);
  }
  std::string normal;
  normal.reserve(path.size() + 1);
  for (const char c : path) {
    const char slash = c == '/' ? '\\' : c;
    if (slash == '\\' && !normal.empty() && normal.back() == '\\') continue;
    normal.push_back(slash >= 'A' && slash <= 'Z' ? char(slash - 'A' + 'a') : slash);
  }
  if (normal.empty() || normal.front() != '\\') normal.insert(normal.begin(), '\\');
  return normal;
}

}  // namespace

bool IsOverriddenGamePath(std::string_view guest_path) {
  // The title's hash table names files relative to a root ("db\gamedb.slt"
  // under media), so a replaced path matches when it ends with this one at a
  // separator.
  const std::string normal = NormalizeGamePath(guest_path);
  std::lock_guard lock(g_overridden_mutex);
  for (const auto& overridden : g_overridden) {
    if (overridden.size() >= normal.size() &&
        overridden.compare(overridden.size() - normal.size(), normal.size(), normal) == 0) {
      return true;
    }
  }
  return false;
}

rex::filesystem::Entry* OverlayDevice::ResolvePath(std::string_view path) {
  if (!path.empty()) {
    for (const auto& overlay : overlays_) {
      rex::filesystem::Entry* entry = overlay->ResolvePath(path);
      // Only files replace; a mod's directories must not hide the game's.
      if (entry && !(entry->attributes() & rex::filesystem::kFileAttributeDirectory)) {
        diagnostics::RecordEvent("mod.file.override",
                                 {{"path", path}, {"from", overlay->host_path().string()}});
        {
          std::lock_guard lock(g_overridden_mutex);
          g_overridden.insert(NormalizeGamePath(path));
        }
        return entry;
      }
    }
  }
  if (auto* entry = base_->ResolvePath(path)) return entry;
  // New assets may introduce directories absent from the disc. VFS file
  // opens resolve the parent first; keep existing base directories intact,
  // but expose an overlay directory when it has no base counterpart.
  for (const auto& overlay : overlays_) {
    if (auto* entry = overlay->ResolvePath(path)) return entry;
  }
  return nullptr;
}

}  // namespace pinyon_shift::mod
