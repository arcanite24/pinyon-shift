#include "save_backups.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <system_error>

#include <fmt/chrono.h>
#include <fmt/format.h>

#include <rex/logging.h>
#include <rex/filesystem.h>

#include "pinyon_shift_diagnostics.h"

namespace pinyon_shift {
namespace fs = std::filesystem;
namespace {

constexpr auto kPollInterval = std::chrono::seconds(5);
constexpr const char* kRestoreFile = "restore-pending.txt";

// Marketplace content is immutable installation data. Keep it out of save
// snapshots and preserve the current installation when restoring an old save.
bool IsMarketplacePath(const fs::path& relative) {
  std::vector<std::string> parts;
  for (const auto& part : relative) parts.push_back(part.string());
  return parts.size() >= 3 && parts[0] == "0000000000000000" &&
         (parts[2] == "00000002" || parts[2] == "Disabled" ||
          (parts[2] == "Headers" && parts.size() >= 4 && parts[3] == "00000002"));
}

std::string UtcStamp() {
  const auto now = std::chrono::system_clock::now();
  return fmt::format("{:%Y%m%dT%H%M%S}Z", std::chrono::floor<std::chrono::seconds>(now));
}

// Copies `from` into a new directory `to` through a temporary sibling, so a
// slot is either complete or absent.
bool CopyTree(const fs::path& from, const fs::path& to) {
  std::error_code error;
  const fs::path staging = fs::path(to) += ".partial";
  fs::remove_all(staging, error);
  fs::create_directories(staging, error);
  for (auto it = fs::recursive_directory_iterator(from, error);
       !error && it != fs::recursive_directory_iterator(); it.increment(error)) {
    const auto relative = it->path().lexically_relative(from);
    if (IsMarketplacePath(relative)) {
      it.disable_recursion_pending();
      continue;
    }
    const auto destination = staging / relative;
    if (it->is_directory(error)) fs::create_directories(destination, error);
    else fs::copy_file(it->path(), destination, fs::copy_options::none, error);
  }
  if (error) {
    REXLOG_ERROR("Save backup: copying {} failed: {}", rex::path_to_utf8(from), error.message());
    fs::remove_all(staging, error);
    return false;
  }
  fs::rename(staging, to, error);
#ifdef _WIN32
  // A newly copied profile can briefly have an open Windows directory handle.
  // Keep publication atomic, and fail normally if the lock does not clear.
  for (int retry = 0; error == std::errc::permission_denied && retry < 20; ++retry) {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    fs::rename(staging, to, error);
  }
#endif
  if (error) {
    REXLOG_ERROR("Save backup: publishing {} failed: {}", rex::path_to_utf8(to), error.message());
    diagnostics::RecordEvent("save.copy.failed",
                             {{"path", rex::path_to_utf8(to)}, {"error", error.message()}});
  }
  return !error;
}

}  // namespace

bool SaveBackups::CopyProfile(const fs::path& from, const fs::path& to) {
  return CopyTree(from, to);
}

SaveBackups::SaveBackups(fs::path user_root, fs::path backup_root, size_t keep)
    : user_root_(std::move(user_root)), backup_root_(std::move(backup_root)), keep_(keep) {}

SaveBackups::~SaveBackups() { Stop(); }

void SaveBackups::Start() {
  if (!thread_.joinable()) {
    thread_ = std::thread(&SaveBackups::Run, this);
  }
}

void SaveBackups::Stop() {
  {
    std::lock_guard lock(mutex_);
    stopping_ = true;
  }
  wake_.notify_all();
  if (thread_.joinable()) {
    thread_.join();
  }
}

SaveBackups::Signature SaveBackups::Scan(const fs::path& root) {
  Signature signature;
  std::error_code error;
  for (auto it = fs::recursive_directory_iterator(root, error);
       !error && it != fs::recursive_directory_iterator(); it.increment(error)) {
    if (IsMarketplacePath(it->path().lexically_relative(root))) {
      it.disable_recursion_pending();
      continue;
    }
    if (!it->is_regular_file(error)) {
      continue;
    }
    ++signature.files;
    signature.bytes += it->file_size(error);
    signature.newest = std::max<int64_t>(
        signature.newest, it->last_write_time(error).time_since_epoch().count());
  }
  return signature;
}

bool SaveBackups::Snapshot(const fs::path& user_root, const fs::path& backup_root,
                           const std::string& reason) {
  std::error_code error;
  if (!fs::exists(user_root, error)) {
    return false;
  }
  fs::create_directories(backup_root, error);
  const std::string name = UtcStamp() + (reason.empty() ? "" : "-" + reason);
  const fs::path slot = backup_root / name;
  if (fs::exists(slot, error) || !CopyTree(user_root, slot / "user")) {
    return false;
  }
  const Signature signature = Scan(slot / "user");
  REXLOG_INFO("Save backup {}: {} files, {} KB", name, signature.files, signature.bytes >> 10);
  diagnostics::RecordEvent("save.backup", {{"slot", name},
                                           {"files", std::to_string(signature.files)},
                                           {"bytes", std::to_string(signature.bytes)}});
  return true;
}

void SaveBackups::Prune() const {
  auto slots = List();
  std::error_code error;
  for (size_t i = keep_; i < slots.size(); ++i) {
    fs::remove_all(slots[i].path, error);
  }
}

std::vector<SaveBackups::Slot> SaveBackups::List() const {
  std::vector<Slot> slots;
  std::error_code error;
  for (auto it = fs::directory_iterator(backup_root_, error);
       !error && it != fs::directory_iterator(); it.increment(error)) {
    if (!it->is_directory(error) || it->path().extension() == ".partial" ||
        !fs::exists(it->path() / "user", error)) {
      continue;
    }
    const Signature signature = Scan(it->path() / "user");
    slots.push_back({it->path().filename().string(), it->path(), signature.files,
                     signature.bytes});
  }
  std::sort(slots.begin(), slots.end(),
            [](const Slot& a, const Slot& b) { return a.name > b.name; });
  return slots;
}

bool SaveBackups::ScheduleRestore(const std::string& slot) const {
  std::error_code error;
  if (slot.find_first_of("/\\") != std::string::npos ||
      !fs::exists(backup_root_ / slot / "user", error)) {
    return false;
  }
  std::ofstream(backup_root_ / kRestoreFile) << slot;
  diagnostics::RecordEvent("save.restore.scheduled", {{"slot", slot}});
  return true;
}

bool SaveBackups::RestorePending() const {
  std::error_code error;
  return fs::exists(backup_root_ / kRestoreFile, error);
}

void SaveBackups::CancelRestore() const {
  std::error_code error;
  fs::remove(backup_root_ / kRestoreFile, error);
}

void SaveBackups::ApplyPendingRestore(const fs::path& user_root, const fs::path& backup_root) {
  std::error_code error;
  const fs::path request = backup_root / kRestoreFile;
  if (!fs::exists(request, error)) {
    return;
  }
  std::string slot;
  std::getline(std::ifstream(request), slot);
  fs::remove(request, error);
  const fs::path source = backup_root / slot / "user";
  if (slot.empty() || slot.find_first_of("/\\") != std::string::npos ||
      !fs::exists(source, error)) {
    REXLOG_ERROR("Save restore: backup {} is missing; nothing restored", slot);
    return;
  }
  // The files being replaced are kept too, so a restore can be undone.
  if (fs::exists(user_root, error) && !Snapshot(user_root, backup_root, "before-restore")) {
    REXLOG_ERROR("Save restore: could not back up the current files; nothing restored");
    return;
  }
  const fs::path staging = fs::path(user_root) += ".restoring";
  fs::remove_all(staging, error);
  if (!CopyTree(source, staging)) {
    REXLOG_ERROR("Save restore: could not copy backup {}", slot);
    return;
  }
  const fs::path previous = fs::path(user_root) += ".replaced";
  fs::remove_all(previous, error);
  if (fs::exists(user_root, error)) {
    fs::rename(user_root, previous, error);
    if (error) {
      REXLOG_ERROR("Save restore: could not retain current files: {}", error.message());
      return;
    }
  }
  // Move only content directories, so restoring a small save never copies
  // gigabytes of DLC or changes which packages the launcher has enabled.
  std::vector<fs::path> moved_content;
  const auto common = previous / "0000000000000000";
  if (fs::exists(common, error)) {
    for (auto it = fs::recursive_directory_iterator(common, error);
         !error && it != fs::recursive_directory_iterator(); it.increment(error)) {
      const auto relative = it->path().lexically_relative(previous);
      if (!IsMarketplacePath(relative)) continue;
      it.disable_recursion_pending();
      fs::create_directories((staging / relative).parent_path(), error);
      if (error) break;
      fs::rename(it->path(), staging / relative, error);
      if (error) break;
      moved_content.push_back(relative);
    }
  }
  if (error) {
    REXLOG_ERROR("Save restore: could not preserve installed DLC: {}", error.message());
    for (auto it = moved_content.rbegin(); it != moved_content.rend(); ++it)
      fs::rename(staging / *it, previous / *it, error);
    fs::rename(previous, user_root, error);
    return;
  }
  fs::rename(staging, user_root, error);
  if (error) {
    REXLOG_ERROR("Save restore: could not put backup {} in place: {}", slot, error.message());
    for (auto it = moved_content.rbegin(); it != moved_content.rend(); ++it)
      fs::rename(staging / *it, previous / *it, error);
    fs::rename(previous, user_root, error);
    return;
  }
  fs::remove_all(previous, error);
  REXLOG_INFO("Save restore: restored backup {}", slot);
  diagnostics::RecordEvent("save.restore.applied", {{"slot", slot}});
}

void SaveBackups::Run() {
  // A backup at the start of each session when the files differ from the
  // newest backup, then one after every save the title completes.
  Signature saved;
  if (auto slots = List(); !slots.empty()) {
    saved = Scan(slots.front().path / "user");
  }
  Signature current = Scan(user_root_);
  if (current.files && !(current.files == saved.files && current.bytes == saved.bytes)) {
    if (Snapshot(user_root_, backup_root_, "session")) {
      Prune();
    }
  }
  saved = current;
  Signature previous = current;
  std::unique_lock lock(mutex_);
  while (!wake_.wait_for(lock, kPollInterval, [this] { return stopping_; })) {
    lock.unlock();
    current = Scan(user_root_);
    // Changed since the last backup and still for a whole poll interval.
    if (current == previous && !(current == saved) && current.files) {
      if (Snapshot(user_root_, backup_root_, "")) {
        Prune();
      }
      saved = current;
    }
    previous = current;
    lock.lock();
  }
}

}  // namespace pinyon_shift
