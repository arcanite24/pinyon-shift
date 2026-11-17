#include "dev_options.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/system/kernel_state.h>

#include "fh1_guest_address.h"
#include "pinyon_shift_diagnostics.h"

// Off by default: each restores the game's own value when turned off.
REXCVAR_DEFINE_BOOL(pinyon_shift_skip_voiceover, false, "Pinyon Shift",
                    "Let A close a dialog before its voice-over ends (the allowskipvoiceover "
                    "developer option)");
REXCVAR_DEFINE_BOOL(pinyon_shift_no_attract_video, false, "Pinyon Shift",
                    "Do not replay the intro movie on an idle title screen (the noattractvideo "
                    "developer option)");
REXCVAR_DEFINE_BOOL(pinyon_shift_no_auto_reset, false, "Pinyon Shift",
                    "Do not reset the car to the road automatically when it leaves it (the "
                    "NoHandOfGodReset developer option)");
// Loading census (docs/CONSOLE_ERA_RESEARCH.md CE-0.3, CE-11 to CE-14).
REXCVAR_DEFINE_BOOL(pinyon_shift_console_option_census, false, "Pinyon Shift",
                    "Log the streaming, file-cache and memory launch options the game booted "
                    "with (console_era.options, base build only)");
REXCVAR_DEFINE_STRING(pinyon_shift_console_option_overrides, "", "Pinyon Shift",
                      "Set streaming, file-cache and memory launch options before the game "
                      "reads them, as name=value pairs separated by commas (base build only; "
                      "for measurements)");
REXCVAR_DEFINE_BOOL(pinyon_shift_photo_camera_through_walls, false, "Pinyon Shift",
                    "Let the photo mode camera pass through walls and terrain (the "
                    "disablephotomodecollisiondetection developer option)");

namespace pinyon_shift::dev_options {

namespace {

struct Option {
  const char* cvar;
  const char* option;
  // Byte offset in the options object; 0 where the build has none.
  uint32_t offset;
};

// Base-disc offsets, from the option visitor sub_824F8150 (each name's
// matcher call receives this + offset). nocameravibration and hidepoipins
// are parsed but no guest code reads them, and skiptutorials gates only the
// Kinect showroom tutorial, so they are not offered; neither is
// allowhighzoomaperture (+4920), which no guest code reads (#488).
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
constexpr std::array<Option, 4> kOptionList = {{
#include "dev_options_v4.inc"
}};
#else
constexpr std::array<Option, 4> kOptionList = {{
    {"pinyon_shift_skip_voiceover", "allowskipvoiceover", 4924},
    {"pinyon_shift_no_attract_video", "noattractvideo", 4222},
    {"pinyon_shift_no_auto_reset", "NoHandOfGodReset", 4937},
    {"pinyon_shift_photo_camera_through_walls", "disablephotomodecollisiondetection", 4921},
}};
#endif


// Launch options that size memory or steer loading and streaming. Offsets are
// base-disc bytes into the options object; the 32-bit ones are set by the
// value matcher, the byte ones are flags. The heap sizes are read by the boot
// arena setup sub_82482E70 (site/findings/systems.toml, "memory arenas sized
// at boot").
enum class Kind { kByte, kWord, kFloat };
struct CensusOption {
  const char* name;
  uint32_t offset;
  Kind kind;
};
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
constexpr std::array<CensusOption, 0> kCensusOptions = {};
#else
constexpr CensusOption kCensusOptions[] = {
    {"maxcarstoloadunified", 2332, Kind::kWord},
    {"streamsize", 2680, Kind::kWord},
    {"streamfragmentationmultiple", 2688, Kind::kFloat},
    {"overridestreamingcpuheapsize", 2692, Kind::kWord},
    {"filecachesize", 2700, Kind::kWord},
    {"filechunksize", 2704, Kind::kWord},
    {"sharedmemorylargepages", 2708, Kind::kByte},
    {"checkzipcrc", 2709, Kind::kByte},
    {"d3dfixedsize", 2712, Kind::kWord},
    {"vehicleheapsize", 2716, Kind::kWord},
    {"nuiheapsize", 2720, Kind::kWord},
    {"compheapsize", 2724, Kind::kWord},
    {"commandbuffersize", 2728, Kind::kWord},
    {"smalltexturesonly", 2738, Kind::kByte},
    {"preloadallmeshes", 2739, Kind::kByte},
    {"audioheapsize", 3136, Kind::kWord},
    {"audioioblocksize", 3140, Kind::kWord},
    {"audiostreamsize", 3144, Kind::kWord},
    {"findzips", 4187, Kind::kByte},
    {"zipprioritybias", 4188, Kind::kWord},
    {"disabledirectoryhashtable", 4192, Kind::kByte},
    {"dvdsafe", 4194, Kind::kByte},
    {"dvdsafecams", 4195, Kind::kByte},
    {"openmpnumthreads", 4224, Kind::kWord},
    {"enablepvspredictahead", 4264, Kind::kByte},
    {"RingBufferSize", 4284, Kind::kWord},
    {"EnableLoadingAlarm", 4560, Kind::kByte},
    {"keepcarpartmemory", 4566, Kind::kByte},
    {"pausephysicsonstreaming", 4868, Kind::kByte},
    {"WhenUnloadingDestroyTrack", 8367, Kind::kByte},
};
#endif

struct State {
  // The game's own value, read before the first write; -1 until then.
  int original = -1;
  bool written = false;
};

std::mutex g_mutex;
std::array<State, kOptionList.size()> g_state;

// In kOptionList's order.
std::array<bool, kOptionList.size()> Wanted() {
  return {REXCVAR_GET(pinyon_shift_skip_voiceover), REXCVAR_GET(pinyon_shift_no_attract_video),
          REXCVAR_GET(pinyon_shift_no_auto_reset),
          REXCVAR_GET(pinyon_shift_photo_camera_through_walls)};
}

uint8_t* Guest(uint32_t address) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return rex::memory::GuestPtr<uint8_t*>(base, address);
}

uint32_t Load32(uint32_t address) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return static_cast<uint32_t>(*rex::memory::GuestPtr<rex::be_u32*>(base, address));
}


std::string ReadCensusOption(uint32_t object, const CensusOption& option) {
  uint8_t* field = Guest(object + option.offset);
  switch (option.kind) {
    case Kind::kByte:
      return std::to_string(int(*field));
    case Kind::kWord:
      return std::to_string(uint32_t(*reinterpret_cast<rex::be_u32*>(field)));
    case Kind::kFloat: {
      const uint32_t bits = *reinterpret_cast<rex::be_u32*>(field);
      float value;
      std::memcpy(&value, &bits, sizeof(value));
      return std::to_string(value);
    }
  }
  return {};
}

void RecordCensus(uint32_t object, const char* phase) {
  std::vector<std::string> values;
  values.reserve(std::size(kCensusOptions));
  std::vector<diagnostics::Field> fields;
  fields.emplace_back("phase", phase);
  for (const CensusOption& option : kCensusOptions) {
    values.push_back(ReadCensusOption(object, option));
    fields.emplace_back(option.name, values.back());
  }
  diagnostics::RecordEvent("console_era.options", fields);
}

void WriteCensusOption(uint32_t object, const CensusOption& option, std::string_view text) {
  uint8_t* field = Guest(object + option.offset);
  const std::string value(text);
  switch (option.kind) {
    case Kind::kByte:
      *field = uint8_t(std::stoul(value));
      break;
    case Kind::kWord:
      *reinterpret_cast<rex::be_u32*>(field) = uint32_t(std::stoul(value));
      break;
    case Kind::kFloat: {
      const float number = std::stof(value);
      uint32_t bits;
      std::memcpy(&bits, &number, sizeof(bits));
      *reinterpret_cast<rex::be_u32*>(field) = bits;
      break;
    }
  }
}

// Applies the overrides once, as soon as the object is built.
void ApplyOverrides(uint32_t object) {
  static bool applied = false;
  if (applied) return;
  applied = true;
  const std::string list = REXCVAR_GET(pinyon_shift_console_option_overrides);
  size_t begin = 0;
  while (begin < list.size()) {
    size_t end = list.find(',', begin);
    if (end == std::string::npos) end = list.size();
    const std::string_view pair(list.data() + begin, end - begin);
    begin = end + 1;
    const size_t equals = pair.find('=');
    if (equals == std::string_view::npos) continue;
    const std::string_view name = pair.substr(0, equals);
    const std::string_view value = pair.substr(equals + 1);
    for (const CensusOption& option : kCensusOptions) {
      if (name != option.name) continue;
      const std::string original = ReadCensusOption(object, option);
      try {
        WriteCensusOption(object, option, value);
      } catch (...) {
        break;
      }
      diagnostics::RecordEvent("console_era.option_set",
                               {{"option", option.name},
                                {"value", ReadCensusOption(object, option)},
                                {"original", original}});
      break;
    }
  }
}

// Logs the options once when the object is first seen and again after the
// boot has used them (3,000 calls: file opens plus title frames).
void UpdateCensus() {
  if (std::size(kCensusOptions) == 0) return;
  const bool census = REXCVAR_GET(pinyon_shift_console_option_census);
  const bool overrides = !std::string(REXCVAR_GET(pinyon_shift_console_option_overrides)).empty();
  if (!census && !overrides) return;
  const uint32_t object = FH1_ADDR(0x832E29A0u);
  if (Load32(object) != FH1_ADDR(0x8200E724u)) return;
  static uint32_t calls = 0;
  if (calls == 0) {
    if (census) RecordCensus(object, "first");
    if (overrides) ApplyOverrides(object);
  }
  if (++calls == 3000 && census) RecordCensus(object, "later");
}

}  // namespace

void Update() {
  if (!rex::system::kernel_state()) return;
  {
    std::lock_guard lock(g_mutex);
    UpdateCensus();
  }
  const auto wanted_list = Wanted();
  static std::atomic<bool> any_written{false};
  const bool any_wanted =
      std::find(wanted_list.begin(), wanted_list.end(), true) != wanted_list.end();
  if (!any_wanted && !any_written.load(std::memory_order_relaxed)) return;
  std::lock_guard lock(g_mutex);
  // Before the constructor runs it would overwrite our bytes with defaults.
  // The launch-options singleton; its vtable word tells the constructor has
  // run (site/findings/systems.toml, launch-options object).
  const uint32_t object = FH1_ADDR(0x832E29A0u);
  if (Load32(object) != FH1_ADDR(0x8200E724u)) return;
  for (size_t i = 0; i < kOptionList.size(); ++i) {
    const Option& option = kOptionList[i];
    if (option.offset == 0) continue;
    State& state = g_state[i];
    uint8_t* flag = Guest(object + option.offset);
    const bool wanted = wanted_list[i];
    if (wanted) {
      if (state.original < 0) state.original = *flag;
      if (*flag != 1) {
        *flag = 1;
        if (!state.written) {
          diagnostics::RecordEvent("dev_option.set",
                                   {{"option", option.option}, {"value", "1"},
                                    {"original", std::to_string(state.original)}});
        }
      }
      state.written = true;
      any_written.store(true, std::memory_order_relaxed);
    } else if (state.written) {
      *flag = uint8_t(state.original < 0 ? 0 : state.original);
      state.written = false;
      diagnostics::RecordEvent("dev_option.set",
                               {{"option", option.option},
                                {"value", std::to_string(int(*flag))}});
    }
  }
}

}  // namespace pinyon_shift::dev_options
