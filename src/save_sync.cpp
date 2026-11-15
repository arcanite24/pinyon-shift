#include "save_sync.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstring>
#include <fstream>
#include <map>
#include <random>
#include <system_error>
#include <unordered_map>

#include <fmt/chrono.h>
#include <fmt/format.h>

#include <rex/filesystem.h>
#include <rex/logging.h>

#include "config/host_config.h"
#include "pinyon_shift_diagnostics.h"
#include "save_backups.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace pinyon_shift {
namespace fs = std::filesystem;
namespace {

constexpr int kFormat = 1;
// History kept per device: enough for a device that missed many of the
// other's sessions to still see it continued from its save.
constexpr size_t kHistory = 64;
constexpr const char* kTitleId = "4D5309C9";
// The build that publishes: a v4 save is one-way, so a base build never
// loads one.
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
constexpr const char* kVersion = "v4";
#else
constexpr const char* kVersion = "base";
#endif
constexpr const char* kAchievementsHeader =
    "# Achievement unlock state - managed by ReXGlue runtime\n";

// ---- SHA-256 (FIPS 180-4) ----------------------------------------------

class Sha256 {
 public:
  Sha256() { Reset(); }
  void Reset() {
    state_ = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
              0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    used_ = 0;
    total_ = 0;
  }
  void Add(const void* data, size_t size) {
    const auto* bytes = static_cast<const uint8_t*>(data);
    total_ += size;
    while (size) {
      const size_t take = std::min(size, block_.size() - used_);
      std::memcpy(block_.data() + used_, bytes, take);
      used_ += take;
      bytes += take;
      size -= take;
      if (used_ == block_.size()) {
        Compress();
        used_ = 0;
      }
    }
  }
  std::string Hex() {
    const uint64_t bits = total_ * 8;
    const uint8_t one = 0x80;
    Add(&one, 1);
    const uint8_t zero = 0;
    while (used_ != 56) Add(&zero, 1);
    uint8_t length[8];
    for (int i = 0; i < 8; ++i) length[i] = uint8_t(bits >> (56 - 8 * i));
    Add(length, 8);
    std::string out;
    for (uint32_t word : state_) out += fmt::format("{:08x}", word);
    return out;
  }

 private:
  static uint32_t Rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
  void Compress() {
    static constexpr uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
      w[i] = uint32_t(block_[4 * i]) << 24 | uint32_t(block_[4 * i + 1]) << 16 |
             uint32_t(block_[4 * i + 2]) << 8 | uint32_t(block_[4 * i + 3]);
    }
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = Rotr(w[i - 15], 7) ^ Rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = Rotr(w[i - 2], 17) ^ Rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    auto [a, b, c, d, e, f, g, h] = state_;
    for (int i = 0; i < 64; ++i) {
      const uint32_t s1 = Rotr(e, 6) ^ Rotr(e, 11) ^ Rotr(e, 25);
      const uint32_t ch = (e & f) ^ (~e & g);
      const uint32_t t1 = h + s1 + ch + k[i] + w[i];
      const uint32_t s0 = Rotr(a, 2) ^ Rotr(a, 13) ^ Rotr(a, 22);
      const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      const uint32_t t2 = s0 + maj;
      h = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = b;
      b = a;
      a = t1 + t2;
    }
    const uint32_t add[8] = {a, b, c, d, e, f, g, h};
    for (int i = 0; i < 8; ++i) state_[i] += add[i];
  }

  std::array<uint32_t, 8> state_;
  std::array<uint8_t, 64> block_{};
  size_t used_ = 0;
  uint64_t total_ = 0;
};

uint32_t Crc32(const uint8_t* data, size_t size, uint32_t crc) {
  static const std::array<uint32_t, 256> table = [] {
    std::array<uint32_t, 256> entries{};
    for (uint32_t n = 0; n < 256; ++n) {
      uint32_t c = n;
      for (int k = 0; k < 8; ++k) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      entries[n] = c;
    }
    return entries;
  }();
  crc = ~crc;
  for (size_t i = 0; i < size; ++i) crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
  return ~crc;
}

// ---- Files -------------------------------------------------------------

struct SaveFile {
  std::string name;  // relative, '/' separated, e.g. B13E.../4D5309C9/...
  fs::path path;
  uint64_t size = 0;
};

// The save's files under a user folder, in name order.
std::vector<SaveFile> ListSave(const fs::path& user_root) {
  std::vector<SaveFile> files;
  std::error_code error;
  for (auto top = fs::directory_iterator(user_root, error);
       !error && top != fs::directory_iterator(); top.increment(error)) {
    std::error_code entry_error;
    if (!top->is_directory(entry_error) || !IsSaveFolder(top->path().filename())) continue;
    for (auto it = fs::recursive_directory_iterator(top->path(), entry_error);
         !entry_error && it != fs::recursive_directory_iterator(); it.increment(entry_error)) {
      std::error_code file_error;
      if (!it->is_regular_file(file_error)) continue;
      SaveFile file;
      file.path = it->path();
      const std::u8string name = it->path().lexically_relative(user_root).generic_u8string();
      file.name.assign(name.begin(), name.end());
      file.size = it->file_size(file_error);
      files.push_back(std::move(file));
    }
  }
  std::sort(files.begin(), files.end(),
            [](const SaveFile& a, const SaveFile& b) { return a.name < b.name; });
  return files;
}

std::optional<std::string> FileSha256(const fs::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return std::nullopt;
  Sha256 sha;
  std::vector<char> buffer(1 << 16);
  while (input) {
    input.read(buffer.data(), std::streamsize(buffer.size()));
    sha.Add(buffer.data(), size_t(input.gcount()));
  }
  return sha.Hex();
}

bool ReplaceFile(const fs::path& temporary, const fs::path& path) {
#ifdef _WIN32
  for (int retry = 0; retry < 20; ++retry) {
    if (MoveFileExW(temporary.c_str(), path.c_str(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
      return true;
    }
    // A sync app may hold the old file open for a moment while it reads it.
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  return false;
#else
  std::error_code error;
  fs::rename(temporary, path, error);
  return !error;
#endif
}

std::string UtcNow() {
  return fmt::format("{:%Y-%m-%dT%H:%M:%S}Z",
                     std::chrono::floor<std::chrono::seconds>(std::chrono::system_clock::now()));
}

std::string MachineName() {
#ifdef _WIN32
  wchar_t name[MAX_COMPUTERNAME_LENGTH + 1];
  DWORD size = MAX_COMPUTERNAME_LENGTH + 1;
  if (GetComputerNameW(name, &size)) return rex::path_to_utf8(fs::path(std::wstring(name, size)));
  return "windows";
#else
  char name[256] = {};
  if (gethostname(name, sizeof(name) - 1) == 0 && name[0]) return name;
  return "device";
#endif
}

const char* Platform() {
#if defined(_WIN32)
  return "windows";
#elif defined(__ANDROID__)
  return "android";
#elif defined(__APPLE__)
  return "macos";
#else
  return "linux";
#endif
}

std::string NewDeviceId() {
  std::random_device random;
  std::string id;
  for (int i = 0; i < 4; ++i) id += fmt::format("{:08x}", uint32_t(random()));
  return id;
}

bool IsDeviceId(std::string_view text) {
  return text.size() == 32 &&
         std::all_of(text.begin(), text.end(), [](char c) { return std::isxdigit(uint8_t(c)); });
}

std::vector<std::string> SplitList(std::string_view text) {
  std::vector<std::string> out;
  while (!text.empty()) {
    const size_t comma = text.find(',');
    std::string item(text.substr(0, comma));
    std::erase_if(item, [](char c) { return std::isspace(uint8_t(c)); });
    if (!item.empty()) out.push_back(std::move(item));
    if (comma == std::string_view::npos) break;
    text.remove_prefix(comma + 1);
  }
  return out;
}

std::string JoinList(const std::vector<std::string>& items) {
  std::string out;
  for (const auto& item : items) {
    if (!out.empty()) out += ',';
    out += item;
  }
  return out;
}

bool Contains(const std::vector<std::string>& list, const std::string& item) {
  return !item.empty() && std::find(list.begin(), list.end(), item) != list.end();
}

std::string Get(const std::string& text, std::string_view name) {
  return config::GetValue(text, name).value_or("");
}

// ---- ZIP (stored members only) -----------------------------------------
// Stored, not deflated: the save's files keep their size and place between
// exports, so a sync app that sends changed blocks (Syncthing) moves only
// the parts the title rewrote.

void Put16(std::string& out, uint32_t value) {
  out.push_back(char(value & 0xFF));
  out.push_back(char((value >> 8) & 0xFF));
}
void Put32(std::string& out, uint32_t value) {
  Put16(out, value & 0xFFFF);
  Put16(out, value >> 16);
}
uint32_t Get16(const uint8_t* p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8; }
uint32_t Get32(const uint8_t* p) { return Get16(p) | Get16(p + 2) << 16; }

// A member name that stays inside the folder it is extracted to.
bool SafeMemberName(std::string_view name) {
  if (name.empty() || name.front() == '/' || name.find('\\') != std::string_view::npos ||
      name.find(':') != std::string_view::npos) {
    return false;
  }
  size_t start = 0;
  while (start <= name.size()) {
    const size_t slash = name.find('/', start);
    const std::string_view part =
        name.substr(start, slash == std::string_view::npos ? std::string_view::npos : slash - start);
    if (part.empty() || part == "." || part == "..") return false;
    if (slash == std::string_view::npos) break;
    start = slash + 1;
  }
  return IsSaveFolder(fs::path(std::string(name.substr(0, name.find('/')))));
}

// ---- Achievements --------------------------------------------------------

// `[unlocked.N]` sections with `filetime = T`, by N.
std::map<uint32_t, uint64_t> ParseAchievements(const std::string& text) {
  std::map<uint32_t, uint64_t> unlocks;
  std::optional<uint32_t> section;
  size_t start = 0;
  while (start < text.size()) {
    size_t end = text.find('\n', start);
    if (end == std::string::npos) end = text.size();
    std::string line = text.substr(start, end - start);
    start = end + 1;
    std::erase_if(line, [](char c) { return c == '\r' || c == ' ' || c == '\t'; });
    if (line.rfind("[unlocked.", 0) == 0 && line.back() == ']') {
      section = uint32_t(std::strtoul(line.c_str() + 10, nullptr, 10));
      unlocks.emplace(*section, 0);
    } else if (line.rfind('[', 0) == 0) {
      section.reset();
    } else if (section && line.rfind("filetime=", 0) == 0) {
      unlocks[*section] = std::strtoull(line.c_str() + 9, nullptr, 10);
    }
  }
  return unlocks;
}

std::string FormatAchievements(const std::map<uint32_t, uint64_t>& unlocks) {
  std::string out = kAchievementsHeader;
  for (const auto& [id, filetime] : unlocks) {
    out += fmt::format("\n[unlocked.{}]\nfiletime = {}\n", id, filetime);
  }
  return out;
}

}  // namespace

// ---- Static helpers --------------------------------------------------------

std::string SaveSync::HashSave(const fs::path& user_root) {
  const auto files = ListSave(user_root);
  if (files.empty()) return {};
  Sha256 sha;
  std::vector<char> buffer(1 << 16);
  for (const auto& file : files) {
    sha.Add(file.name.data(), file.name.size() + 1);  // with the terminator
    uint8_t size[8];
    for (int i = 0; i < 8; ++i) size[i] = uint8_t(file.size >> (8 * i));
    sha.Add(size, 8);
    std::ifstream input(file.path, std::ios::binary);
    if (!input) return {};
    uint64_t left = file.size;
    while (left && input) {
      input.read(buffer.data(), std::streamsize(std::min<uint64_t>(left, buffer.size())));
      const auto got = size_t(input.gcount());
      sha.Add(buffer.data(), got);
      left -= got;
    }
    if (left) return {};  // the file shrank while being read
  }
  return sha.Hex();
}

bool SaveSync::WriteArchive(const fs::path& user_root, const fs::path& archive) {
  const auto files = ListSave(user_root);
  if (files.empty()) return false;
  const fs::path temporary = fs::path(archive).replace_filename(
      "." + rex::path_to_utf8(archive.filename()) + ".tmp");
  std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
  if (!out) return false;
  std::string central;
  uint64_t offset = 0;
  std::vector<char> buffer(1 << 16);
  for (const auto& file : files) {
    std::ifstream input(file.path, std::ios::binary);
    std::string data;
    data.resize(size_t(file.size));
    if (!input || !input.read(data.data(), std::streamsize(data.size()))) return false;
    if (offset + data.size() > 0xFFFFFFF0ull) return false;  // needs ZIP64; saves are far smaller
    const uint32_t crc = Crc32(reinterpret_cast<const uint8_t*>(data.data()), data.size(), 0);
    // Fixed time (1980-01-01): the archive's bytes depend on the save only.
    std::string local;
    Put32(local, 0x04034b50);
    Put16(local, 10);      // version needed
    Put16(local, 0x0800);  // UTF-8 names
    Put16(local, 0);       // stored
    Put16(local, 0);
    Put16(local, 0x21);
    Put32(local, crc);
    Put32(local, uint32_t(data.size()));
    Put32(local, uint32_t(data.size()));
    Put16(local, uint32_t(file.name.size()));
    Put16(local, 0);
    local += file.name;
    out.write(local.data(), std::streamsize(local.size()));
    out.write(data.data(), std::streamsize(data.size()));

    Put32(central, 0x02014b50);
    Put16(central, 20);
    Put16(central, 10);
    Put16(central, 0x0800);
    Put16(central, 0);
    Put16(central, 0);
    Put16(central, 0x21);
    Put32(central, crc);
    Put32(central, uint32_t(data.size()));
    Put32(central, uint32_t(data.size()));
    Put16(central, uint32_t(file.name.size()));
    Put16(central, 0);
    Put16(central, 0);
    Put16(central, 0);
    Put16(central, 0);
    Put32(central, 0);
    Put32(central, uint32_t(offset));
    central += file.name;
    offset += local.size() + data.size();
  }
  std::string end;
  Put32(end, 0x06054b50);
  Put16(end, 0);
  Put16(end, 0);
  Put16(end, uint32_t(files.size()));
  Put16(end, uint32_t(files.size()));
  Put32(end, uint32_t(central.size()));
  Put32(end, uint32_t(offset));
  Put16(end, 0);
  out.write(central.data(), std::streamsize(central.size()));
  out.write(end.data(), std::streamsize(end.size()));
  out.close();
  if (!out) {
    std::error_code error;
    fs::remove(temporary, error);
    return false;
  }
  if (!ReplaceFile(temporary, archive)) {
    std::error_code error;
    fs::remove(temporary, error);
    return false;
  }
  return true;
}

bool SaveSync::ExtractArchive(const fs::path& archive, const fs::path& to) {
  std::ifstream input(archive, std::ios::binary);
  if (!input) return false;
  std::string bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  const auto* data = reinterpret_cast<const uint8_t*>(bytes.data());
  if (bytes.size() < 22) return false;
  size_t eocd = bytes.size() - 22;
  while (Get32(data + eocd) != 0x06054b50) {
    if (eocd == 0 || bytes.size() - eocd > 22 + 0xFFFF) return false;
    --eocd;
  }
  const uint32_t count = Get16(data + eocd + 10);
  size_t at = Get32(data + eocd + 16);
  std::error_code error;
  for (uint32_t i = 0; i < count; ++i) {
    if (at + 46 > bytes.size() || Get32(data + at) != 0x02014b50) return false;
    const uint32_t method = Get16(data + at + 10);
    const uint32_t crc = Get32(data + at + 16);
    const uint32_t compressed = Get32(data + at + 20);
    const uint32_t size = Get32(data + at + 24);
    const uint32_t name_length = Get16(data + at + 28);
    const uint32_t extra = Get16(data + at + 30);
    const uint32_t comment = Get16(data + at + 32);
    const uint32_t local = Get32(data + at + 42);
    if (at + 46 + name_length > bytes.size()) return false;
    const std::string name(bytes.data() + at + 46, name_length);
    at += 46 + name_length + extra + comment;
    if (method != 0 || compressed != size || !SafeMemberName(name)) return false;
    if (size_t(local) + 30 > bytes.size() || Get32(data + local) != 0x04034b50) return false;
    const size_t start = local + 30 + Get16(data + local + 26) + Get16(data + local + 28);
    if (start + size > bytes.size()) return false;
    if (Crc32(data + start, size, 0) != crc) return false;
    const fs::path target = to / fs::path(std::u8string(name.begin(), name.end()));
    fs::create_directories(target.parent_path(), error);
    std::ofstream out(target, std::ios::binary | std::ios::trunc);
    out.write(bytes.data() + start, size);
    if (!out) return false;
  }
  return true;
}

uint64_t SaveSync::MergeAchievements(const fs::path& into, const fs::path& from) {
  const auto incoming = config::ReadFile(from);
  if (!incoming) return 0;
  const std::string current = config::ReadFile(into).value_or("");
  auto unlocks = ParseAchievements(current);
  bool changed = false;
  uint64_t gained = 0;
  for (const auto& [id, filetime] : ParseAchievements(*incoming)) {
    auto [it, inserted] = unlocks.emplace(id, filetime);
    if (inserted) {
      ++gained;
      changed = true;
    } else if (filetime && (it->second == 0 || filetime < it->second)) {
      it->second = filetime;
      changed = true;
    }
  }
  if (changed) {
    std::error_code error;
    fs::create_directories(into.parent_path(), error);
    if (!config::WriteAtomically(into, FormatAchievements(unlocks))) return 0;
  }
  return gained;
}

// ---- State -------------------------------------------------------------------

SaveSync::SaveSync(fs::path user_root, fs::path state_root, fs::path folder,
                   std::string device_name)
    : user_root_(std::move(user_root)),
      state_root_(std::move(state_root)),
      folder_(std::move(folder)),
      device_name_(std::move(device_name)) {}

SaveSync::~SaveSync() { StopWatching(); }

std::string SaveSync::device_name() const {
  return device_name_.empty() ? MachineName() : device_name_;
}

fs::path SaveSync::StatePath() const { return state_root_ / "config" / "save_sync.toml"; }
fs::path SaveSync::BackupRoot() const { return state_root_ / "backups" / "saves"; }

SaveSync::State SaveSync::LoadState() const {
  const std::string text = config::ReadFile(StatePath()).value_or("");
  State state;
  state.id = Get(text, "device_id");
  state.machine = Get(text, "machine");
  state.current = Get(text, "current");
  state.history = SplitList(Get(text, "history"));
  state.last_export = Get(text, "last_export");
  state.published_hash = Get(text, "published_hash");
  state.republish = Get(text, "republish") == "true";
  // A copied or cloned user folder (a new machine) gets its own identity,
  // so two devices never write the same files.
  const std::string machine = MachineName();
  if (!IsDeviceId(state.id) || state.machine != machine) {
    if (!state.id.empty()) {
      REXLOG_INFO("Save sync: this user folder moved to {}; new device id", machine);
    }
    state.id = NewDeviceId();
    state.machine = machine;
    state.published_hash.clear();
    state.last_export.clear();
  }
  return state;
}

bool SaveSync::SaveState(const State& state) const {
  std::string text = config::ReadFile(StatePath()).value_or(
      "# Save sync state (docs/SAVE_SYNC.md); written by the game.\n");
  text = config::SetValue(text, "device_id", config::Quote(state.id));
  text = config::SetValue(text, "machine", config::Quote(state.machine));
  text = config::SetValue(text, "current", config::Quote(state.current));
  text = config::SetValue(text, "history", config::Quote(JoinList(state.history)));
  text = config::SetValue(text, "last_export", config::Quote(state.last_export));
  text = config::SetValue(text, "published_hash", config::Quote(state.published_hash));
  text = config::SetValue(text, "republish", state.republish ? "true" : "false");
  std::error_code error;
  fs::create_directories(StatePath().parent_path(), error);
  return config::WriteAtomically(StatePath(), text);
}

void SaveSync::Advance(State& state, const std::string& hash) {
  if (hash.empty() || hash == state.current) return;
  if (!state.current.empty()) {
    std::erase(state.history, state.current);
    state.history.insert(state.history.begin(), state.current);
  }
  std::erase(state.history, hash);
  if (state.history.size() > kHistory) state.history.resize(kHistory);
  state.current = hash;
}

bool SaveSync::FolderUsable() const {
  std::error_code error;
  if (folder_.empty() || !fs::is_directory(folder_, error)) return false;
  fs::create_directories(DevicesDir(), error);
  return fs::is_directory(DevicesDir(), error);
}

namespace {
SaveSync::Relation RelationTo(const std::string& current,
                              const std::vector<std::string>& history,
                              const SaveSync::Remote& remote) {
  using Relation = SaveSync::Relation;
  if (remote.save_hash == current) return Relation::kSame;
  if (Contains(history, remote.save_hash)) return Relation::kLocalAhead;
  if (current.empty() || Contains(remote.history, current)) return Relation::kRemoteAhead;
  return Relation::kDiverged;
}

// Archive hashes by path, size and time, so polling does not reread them.
struct CachedHash {
  uint64_t size = 0;
  int64_t time = 0;
  std::string sha;
};
std::mutex g_hash_cache_mutex;
std::unordered_map<std::string, CachedHash> g_hash_cache;

std::optional<std::string> CachedFileSha256(const fs::path& path, uint64_t size) {
  std::error_code error;
  const int64_t time = fs::last_write_time(path, error).time_since_epoch().count();
  if (error) return std::nullopt;
  const std::string key = rex::path_to_utf8(path);
  {
    std::lock_guard lock(g_hash_cache_mutex);
    auto it = g_hash_cache.find(key);
    if (it != g_hash_cache.end() && it->second.size == size && it->second.time == time) {
      return it->second.sha;
    }
  }
  auto sha = FileSha256(path);
  if (sha) {
    std::lock_guard lock(g_hash_cache_mutex);
    g_hash_cache[key] = {size, time, *sha};
  }
  return sha;
}
}  // namespace

std::vector<SaveSync::Remote> SaveSync::ReadRemotes(const State& state) const {
  std::vector<Remote> remotes;
  std::error_code error;
  for (auto it = fs::directory_iterator(DevicesDir(), error);
       !error && it != fs::directory_iterator(); it.increment(error)) {
    const fs::path& path = it->path();
    const std::string id = rex::path_to_utf8(path.stem());
    // Only "<32 hex>.toml": a sync app's conflict copy or our own file is
    // never read as a device.
    if (path.extension() != ".toml" || !IsDeviceId(id) || id == state.id) continue;
    const auto text = config::ReadFile(path);
    if (!text) continue;
    const int format = std::atoi(Get(*text, "format").c_str());
    if (Get(*text, "device_id") != id) continue;
    if (format != kFormat) {
      REXLOG_WARN("Save sync: {} uses save format {}; update Pinyon Shift on this device",
                  Get(*text, "device_name"), format);
      continue;
    }
    Remote remote;
    remote.device_id = id;
    remote.device_name = Get(*text, "device_name");
    remote.platform = Get(*text, "platform");
    remote.written_utc = Get(*text, "written_utc");
    remote.save_hash = Get(*text, "save_hash");
    remote.history = SplitList(Get(*text, "history"));
    remote.achievements = std::strtoull(Get(*text, "achievements").c_str(), nullptr, 10);
    remote.version = Get(*text, "version");
    if (remote.version.empty()) remote.version = "base";
    remote.loadable = remote.version == kVersion || remote.version == "base";
    // The archive must be the one the manifest describes: a sync app may
    // deliver the manifest first, or a partial archive.
    const fs::path archive = DevicesDir() / (id + ".lsave");
    const uint64_t bytes = std::strtoull(Get(*text, "archive_bytes").c_str(), nullptr, 10);
    std::error_code size_error;
    if (remote.save_hash.empty() || fs::file_size(archive, size_error) != bytes || size_error) {
      continue;
    }
    const auto sha = CachedFileSha256(archive, bytes);
    if (!sha || *sha != Get(*text, "archive_sha256")) continue;
    remote.relation = RelationTo(state.current, state.history, remote);
    remotes.push_back(std::move(remote));
  }
  std::sort(remotes.begin(), remotes.end(),
            [](const Remote& a, const Remote& b) { return a.written_utc > b.written_utc; });
  return remotes;
}

bool SaveSync::Import(State& state, const Remote& remote) {
  std::error_code error;
  if (!remote.loadable) return false;
  const fs::path staging_root = state_root_ / "backups" / "sync-incoming";
  const fs::path staging = staging_root / "user";
  fs::remove_all(staging_root, error);
  fs::create_directories(staging_root, error);
  const auto cleanup = [&] { fs::remove_all(staging_root, error); };
  // Pinyon's restore puts a whole user tree in place (keeping the installed
  // DLC), so the staged tree is this device's, with its profile folders
  // replaced by the archive's: the achievements and content headers stay.
  bool staged = SaveBackups::CopyProfile(user_root_, staging);
  for (auto it = fs::directory_iterator(staging, error);
       staged && !error && it != fs::directory_iterator(); it.increment(error)) {
    std::error_code remove_error;
    if (IsSaveFolder(it->path().filename())) fs::remove_all(it->path(), remove_error);
  }
  if (!staged || !ExtractArchive(DevicesDir() / (remote.device_id + ".lsave"), staging) ||
      HashSave(staging) != remote.save_hash) {
    REXLOG_ERROR("Save sync: the save from {} is damaged; not loaded", remote.device_name);
    diagnostics::RecordEvent("sync.import.failed",
                             {{"device", remote.device_name}, {"reason", "archive"}});
    cleanup();
    return false;
  }
  // Through a backup slot, so the save restore swaps it in (backing up the
  // current save first) and the imported save stays in the backup list.
  const auto slot = SaveBackups::AddSlot(staging, BackupRoot(), "sync");
  cleanup();
  if (!slot || !SaveBackups::RestoreSlot(user_root_, BackupRoot(), *slot)) {
    REXLOG_ERROR("Save sync: could not put the save from {} in place", remote.device_name);
    diagnostics::RecordEvent("sync.import.failed",
                             {{"device", remote.device_name}, {"reason", "restore"}});
    return false;
  }
  Advance(state, remote.save_hash);
  for (const auto& hash : remote.history) {
    if (!Contains(state.history, hash) && hash != state.current &&
        state.history.size() < kHistory) {
      state.history.push_back(hash);
    }
  }
  state.republish = true;
  REXLOG_INFO("Save sync: loaded the save from {} ({})", remote.device_name, remote.written_utc);
  diagnostics::RecordEvent("sync.import", {{"device", remote.device_name},
                                           {"written", remote.written_utc}});
  return true;
}

bool SaveSync::ExportLocked(State& state, const fs::path& save_root) {
  if (!FolderUsable()) return false;
  const std::string hash = HashSave(save_root);
  if (hash.empty()) return false;
  Advance(state, hash);
  const fs::path manifest = DevicesDir() / (state.id + ".toml");
  std::error_code error;
  if (state.published_hash == hash && !state.republish && fs::exists(manifest, error)) {
    return true;
  }
  const fs::path archive = DevicesDir() / (state.id + ".lsave");
  if (!WriteArchive(save_root, archive)) {
    REXLOG_ERROR("Save sync: could not write {}", rex::path_to_utf8(archive));
    diagnostics::RecordEvent("sync.export.failed", {{"path", rex::path_to_utf8(archive)}});
    return false;
  }
  const auto sha = FileSha256(archive);
  const uint64_t bytes = fs::file_size(archive, error);
  if (!sha || error) return false;
  // The unlocks travel beside the save (they are merged, never chosen).
  const fs::path achievements = user_root_ / "achievements" / (std::string(kTitleId) + ".toml");
  const auto unlocks = config::ReadFile(achievements);
  uint64_t unlocked = 0;
  if (unlocks) {
    unlocked = ParseAchievements(*unlocks).size();
    config::WriteAtomically(DevicesDir() / (state.id + ".achievements.toml"), *unlocks);
  }
  state.last_export = UtcNow();
  std::string text = "# Pinyon Shift save sync manifest (docs/SAVE_SYNC.md). Do not edit.\n";
  text = config::SetValue(text, "format", std::to_string(kFormat));
  text = config::SetValue(text, "device_id", config::Quote(state.id));
  text = config::SetValue(text, "device_name", config::Quote(device_name()));
  text = config::SetValue(text, "platform", config::Quote(Platform()));
  text = config::SetValue(text, "version", config::Quote(kVersion));
  text = config::SetValue(text, "written_utc", config::Quote(state.last_export));
  text = config::SetValue(text, "save_hash", config::Quote(hash));
  text = config::SetValue(text, "based_on",
                          config::Quote(state.history.empty() ? "" : state.history.front()));
  text = config::SetValue(text, "history", config::Quote(JoinList(state.history)));
  text = config::SetValue(text, "archive_sha256", config::Quote(*sha));
  text = config::SetValue(text, "archive_bytes", std::to_string(bytes));
  text = config::SetValue(text, "achievements", std::to_string(unlocked));
  if (!config::WriteAtomically(manifest, text)) {
    REXLOG_ERROR("Save sync: could not write {}", rex::path_to_utf8(manifest));
    return false;
  }
  state.published_hash = hash;
  state.republish = false;
  SaveState(state);
  REXLOG_INFO("Save sync: published this device's save ({} KB)", bytes >> 10);
  diagnostics::RecordEvent("sync.export", {{"bytes", std::to_string(bytes)}});
  return true;
}

// ---- Public ------------------------------------------------------------------

SaveSync::StartupResult SaveSync::Startup() {
  std::lock_guard lock(mutex_);
  StartupResult result;
  if (!FolderUsable()) {
    REXLOG_WARN("Save sync: folder {} is not reachable; saves are not synced this session",
                rex::path_to_utf8(folder_));
    diagnostics::RecordEvent("sync.unavailable", {{"folder", rex::path_to_utf8(folder_)}});
    result.folder_unavailable = true;
    return result;
  }
  State state = LoadState();
  // Progress made while sync was off, or since the last export (a crash):
  // it continued from the save this device last had.
  const std::string live = HashSave(user_root_);
  Advance(state, live);
  if (live.empty()) state.current.clear();

  std::vector<Remote> remotes = ReadRemotes(state);

  // Achievements: every device's unlocks, whichever save is kept.
  const fs::path achievements = user_root_ / "achievements" / (std::string(kTitleId) + ".toml");
  for (const auto& remote : remotes) {
    result.achievements_merged +=
        MergeAchievements(achievements, DevicesDir() / (remote.device_id + ".achievements.toml"));
  }

  // The player's choice from the SAVE SYNC page.
  const std::string text = config::ReadFile(StatePath()).value_or("");
  const std::string pending = Get(text, "import_pending");
  const Remote* chosen = nullptr;
  if (!pending.empty()) {
    for (const auto& remote : remotes) {
      if (remote.device_id == pending && remote.loadable) chosen = &remote;
    }
    if (!chosen) REXLOG_WARN("Save sync: the chosen device's save is not here; nothing loaded");
  } else {
    // A save that continued from this one (or any, when this device has
    // none) loads without asking, when exactly one is newest.
    std::vector<const Remote*> ahead;
    for (const auto& remote : remotes) {
      if (remote.relation == Relation::kRemoteAhead && remote.loadable) ahead.push_back(&remote);
    }
    std::vector<const Remote*> newest;
    for (const Remote* candidate : ahead) {
      const bool superseded = std::any_of(ahead.begin(), ahead.end(), [&](const Remote* other) {
        return other != candidate && (Contains(other->history, candidate->save_hash) ||
                                      (other->save_hash == candidate->save_hash &&
                                       other->written_utc > candidate->written_utc));
      });
      if (!superseded) newest.push_back(candidate);
    }
    if (newest.size() == 1) chosen = newest.front();
  }
  if (chosen && Import(state, *chosen)) {
    result.imported_from = chosen->device_name;
  }
  if (!pending.empty()) {
    std::string cleared = config::ReadFile(StatePath()).value_or("");
    cleared = config::SetValue(cleared, "import_pending", "\"\"");
    config::WriteAtomically(StatePath(), cleared);
  }
  for (auto& remote : remotes) {
    remote.relation = RelationTo(state.current, state.history, remote);
    // A newer save still not loaded (two newest that differ, so neither
    // loads on its own) is a choice too.
    if (remote.loadable &&
        (remote.relation == Relation::kDiverged || remote.relation == Relation::kRemoteAhead)) {
      result.diverged.push_back(remote);
    }
  }
  SaveState(state);
  // Publish what this device starts with (the title is not running yet).
  ExportLocked(state, user_root_);
  SaveState(state);
  return result;
}

bool SaveSync::Export(const fs::path& save_root) {
  std::lock_guard lock(mutex_);
  State state = LoadState();
  return ExportLocked(state, save_root);
}

std::vector<SaveSync::Remote> SaveSync::Remotes() const {
  std::lock_guard lock(mutex_);
  if (!FolderUsable()) return {};
  return ReadRemotes(LoadState());
}

bool SaveSync::ScheduleImport(const std::string& device_id) {
  std::lock_guard lock(mutex_);
  if (!IsDeviceId(device_id)) return false;
  const auto remotes = ReadRemotes(LoadState());
  if (std::none_of(remotes.begin(), remotes.end(), [&](const Remote& remote) {
        return remote.device_id == device_id && remote.loadable;
      })) {
    return false;
  }
  std::string text = config::ReadFile(StatePath()).value_or("");
  text = config::SetValue(text, "import_pending", config::Quote(device_id));
  diagnostics::RecordEvent("sync.import.scheduled", {{"device", device_id}});
  return config::WriteAtomically(StatePath(), text);
}

std::optional<std::string> SaveSync::ImportPending() const {
  std::lock_guard lock(mutex_);
  const std::string pending = Get(config::ReadFile(StatePath()).value_or(""), "import_pending");
  if (pending.empty()) return std::nullopt;
  return pending;
}

void SaveSync::CancelImport() {
  std::lock_guard lock(mutex_);
  std::string text = config::ReadFile(StatePath()).value_or("");
  text = config::SetValue(text, "import_pending", "\"\"");
  config::WriteAtomically(StatePath(), text);
}

bool SaveSync::KeepLocal(const std::string& device_id) {
  std::lock_guard lock(mutex_);
  State state = LoadState();
  for (const auto& remote : ReadRemotes(state)) {
    if (remote.device_id != device_id || !remote.loadable) continue;
    // The other save, and what it descends from, count as replaced by this
    // device's: once published, the other device fast-forwards to it.
    if (!Contains(state.history, remote.save_hash) && remote.save_hash != state.current) {
      state.history.insert(state.history.begin(), remote.save_hash);
    }
    for (const auto& hash : remote.history) {
      if (!Contains(state.history, hash) && hash != state.current &&
          state.history.size() < kHistory) {
        state.history.push_back(hash);
      }
    }
    if (state.history.size() > kHistory) state.history.resize(kHistory);
    state.republish = true;
    diagnostics::RecordEvent("sync.keep_local", {{"device", remote.device_name}});
    return SaveState(state);
  }
  return false;
}

std::string SaveSync::LastExportUtc() const {
  std::lock_guard lock(mutex_);
  return Get(config::ReadFile(StatePath()).value_or(""), "last_export");
}

void SaveSync::Watch(std::function<void(const std::vector<Remote>&, bool)> on_poll,
                     std::chrono::seconds first, std::chrono::seconds interval) {
  StopWatching();
  {
    std::lock_guard lock(watch_mutex_);
    watch_stopping_ = false;
  }
  watcher_ = std::thread([this, on_poll = std::move(on_poll), first, interval] {
    // What the player was already told about, by device and save.
    std::vector<std::string> told;
    bool first_poll = true;
    std::unique_lock lock(watch_mutex_);
    while (!watch_wake_.wait_for(lock, first_poll ? first : interval,
                                 [this] { return watch_stopping_; })) {
      lock.unlock();
      std::vector<Remote> news;
      for (const auto& remote : Remotes()) {
        if (!remote.loadable ||
            (remote.relation != Relation::kRemoteAhead && remote.relation != Relation::kDiverged)) {
          continue;
        }
        const std::string key = remote.device_id + ":" + remote.save_hash;
        if (!Contains(told, key)) {
          told.push_back(key);
          news.push_back(remote);
        }
      }
      if (on_poll && (first_poll || !news.empty())) on_poll(news, first_poll);
      first_poll = false;
      lock.lock();
    }
  });
}

void SaveSync::StopWatching() {
  {
    std::lock_guard lock(watch_mutex_);
    watch_stopping_ = true;
  }
  watch_wake_.notify_all();
  if (watcher_.joinable()) watcher_.join();
}

}  // namespace pinyon_shift
