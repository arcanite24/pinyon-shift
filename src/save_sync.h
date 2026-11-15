#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace pinyon_shift {

// Save sync through a folder a sync app (Syncthing, Dropbox, OneDrive, ...)
// keeps in step between devices (docs/SAVE_SYNC.md; ported from Lavender
// Shift). Each device writes only its own files in <folder>/devices, so the
// sync app never sees two writers of one file:
//   <id>.lsave              the save: a stored ZIP of the profile folders
//   <id>.achievements.toml  the achievement unlocks
//   <id>.toml               the manifest, written last
// The live save is read only when the title is not writing it (a backup
// snapshot, or at start and exit) and replaced only at start, before the
// title runs, through the save backups' restore (so the replaced save is
// itself backed up). Which save is newer comes from lineage, never clocks:
// each manifest lists the save hashes the device's save descends from (or
// replaced by the player's choice). A v4 save is one-way (the base game
// cannot load it), so a base build never loads a save a v4 build published.
class SaveSync {
 public:
  enum class Relation {
    kSame,         // both devices have this save
    kRemoteAhead,  // the other device continued from this device's save
    kLocalAhead,   // this device continued from the other's save
    kDiverged,     // both played since they last had the same save
  };

  struct Remote {
    std::string device_id, device_name, platform;
    std::string written_utc;  // "2026-11-14T18:02:11Z"
    std::string save_hash;
    std::vector<std::string> history;
    uint64_t achievements = 0;
    Relation relation = Relation::kSame;
    // "base" or "v4": the build that published it. False when this build
    // cannot load it (a v4 save on a base build); it is listed, never loaded.
    std::string version;
    bool loadable = true;
  };

  struct StartupResult {
    // The save imported from another device without asking (it continued
    // from this one's); empty when none was.
    std::string imported_from;
    // Saves that differ from this device's and need the player's choice.
    std::vector<Remote> diverged;
    // Achievement unlocks merged in from other devices.
    uint64_t achievements_merged = 0;
    // The folder was set but could not be used (missing, unwritable).
    bool folder_unavailable = false;
  };

  // `user_root` is the player's own save tree (<state>/user); the sync
  // state and the backups live under `state_root`. `device_name` empty uses
  // the machine's name.
  SaveSync(std::filesystem::path user_root, std::filesystem::path state_root,
           std::filesystem::path folder, std::string device_name);
  ~SaveSync();

  const std::filesystem::path& folder() const { return folder_; }
  std::string device_name() const;

  // At start, before the title runs: applies an import the player chose,
  // imports a save that continued from this one, merges achievements and
  // publishes this device's save when it changed.
  StartupResult Startup();

  // Publishes the save in `save_root` (a user folder: the live one when the
  // title is not writing it, or a backup snapshot's copy). Skipped when that
  // save is already published, unless the player's choice changed the
  // history since.
  bool Export(const std::filesystem::path& save_root);

  // The other devices' published saves whose files are complete, as seen
  // from this device's save.
  std::vector<Remote> Remotes() const;

  // Imports `device_id`'s save at the next start (this device's save is
  // backed up first).
  bool ScheduleImport(const std::string& device_id);
  std::optional<std::string> ImportPending() const;  // the device id
  void CancelImport();
  // Keeps this device's save over `device_id`'s: the other save counts as
  // replaced, so neither device asks again once this one publishes.
  bool KeepLocal(const std::string& device_id);

  // Polls the folder, `first` after starting and then every `interval`,
  // and calls `on_poll` with the saves of other devices that this one does
  // not have and that it was not told about before (`first_poll` on the
  // first call, which is made even when there are none).
  void Watch(std::function<void(const std::vector<Remote>& news, bool first_poll)> on_poll,
             std::chrono::seconds first = std::chrono::seconds(15),
             std::chrono::seconds interval = std::chrono::seconds(30));
  void StopWatching();

  // The last time this device published, "" when never.
  std::string LastExportUtc() const;

  // Exposed for tests.
  static std::string HashSave(const std::filesystem::path& user_root);
  static bool WriteArchive(const std::filesystem::path& user_root,
                           const std::filesystem::path& archive);
  static bool ExtractArchive(const std::filesystem::path& archive,
                             const std::filesystem::path& to);
  // `into` gains the unlocks only `from` has (keeping the earliest time of
  // each); returns how many it gained, and writes `into` only then.
  static uint64_t MergeAchievements(const std::filesystem::path& into,
                                    const std::filesystem::path& from);

 private:
  struct State {
    std::string id, machine, current, last_export, published_hash;
    std::vector<std::string> history;
    bool republish = false;  // the history changed since the last export
  };
  std::filesystem::path StatePath() const;
  std::filesystem::path DevicesDir() const { return folder_ / "devices"; }
  std::filesystem::path BackupRoot() const;
  State LoadState() const;
  bool SaveState(const State& state) const;
  // Records `hash` as this device's save, keeping the old one in history.
  static void Advance(State& state, const std::string& hash);
  std::vector<Remote> ReadRemotes(const State& state) const;
  bool Import(State& state, const Remote& remote);
  bool ExportLocked(State& state, const std::filesystem::path& save_root);
  bool FolderUsable() const;

  std::filesystem::path user_root_;
  std::filesystem::path state_root_;
  std::filesystem::path folder_;
  std::string device_name_;
  mutable std::mutex mutex_;

  std::thread watcher_;
  std::mutex watch_mutex_;
  std::condition_variable watch_wake_;
  bool watch_stopping_ = false;
};

}  // namespace pinyon_shift
