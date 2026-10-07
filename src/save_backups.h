#pragma once

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <filesystem>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace pinyon_shift {

// In-game save backups (NP-5.5). Saves are plain files under the state's
// `user` directory. Backups exclude Marketplace installations and their headers;
// restoring preserves the currently installed/enabled DLC. A background thread
// snapshots it once the title has written it and the files have been still
// for a few seconds (so a save in progress is never copied half-written),
// keeping the newest `keep` snapshots under `backup_root`. Restoring is only
// ever scheduled by the player and happens at the next start, before the
// title runs, after the current files are themselves backed up.
class SaveBackups {
 public:
  struct Slot {
    std::string name;  // directory name: UTC time, plus a reason suffix
    std::filesystem::path path;
    uint64_t files = 0;
    uint64_t bytes = 0;
  };

  SaveBackups(std::filesystem::path user_root, std::filesystem::path backup_root,
              size_t keep = 10);
  ~SaveBackups();

  void Start();
  void Stop();

  // Newest first.
  std::vector<Slot> List() const;
  // Restores `slot` at the next start; false when it does not exist.
  bool ScheduleRestore(const std::string& slot) const;
  bool RestorePending() const;
  void CancelRestore() const;

  // At startup, before the title runs: applies a scheduled restore.
  static void ApplyPendingRestore(const std::filesystem::path& user_root,
                                  const std::filesystem::path& backup_root);

  // Create a new isolated profile, excluding shared Marketplace installations.
  static bool CopyProfile(const std::filesystem::path& from,
                          const std::filesystem::path& to);

 private:
  struct Signature {
    uint64_t files = 0, bytes = 0;
    int64_t newest = 0;
    bool operator==(const Signature&) const = default;
  };
  static Signature Scan(const std::filesystem::path& root);
  static bool Snapshot(const std::filesystem::path& user_root,
                       const std::filesystem::path& backup_root, const std::string& reason);
  void Prune() const;
  void Run();

  std::filesystem::path user_root_;
  std::filesystem::path backup_root_;
  size_t keep_;
  std::thread thread_;
  std::mutex mutex_;
  std::condition_variable wake_;
  bool stopping_ = false;
};

}  // namespace pinyon_shift
