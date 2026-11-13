---
title: Methods and tools
section: Reverse engineering
order: 2
description: How Pinyon Shift finds out what Forza Horizon's code and data do, from reading strings and RTTI to probe hooks, scripted A/B runs and mapping addresses to the title update, with the code to repeat each step.
---

# Methods and tools

Most findings come from the same loop: ask a narrow question, read what the executable and data files already say, probe the running game, check the answer on a scripted route, and write it down. The recompiled game makes the middle steps cheaper than on a console: every guest function is a C++ function that can be read, searched and hooked, and the whole game runs under a debugger and a profiler.

{{diagram:game-research-workflow|The research loop. A record is written whether the answer is yes or no.}}

## Reading the executable

### Strings and RTTI

The executable keeps MSVC run-time type information: about 6,800 class names in `.rdata`, with vtables and base classes. A class name is usually the fastest way into a subsystem (`CTrackPVSZoneResource`, `CActivityBarnFind`), and the names nested inside a class show what it does: `CParams1IRenderThreadEnableShadowsInternal@CRenderThreadLink` is a command with one argument that switches shadows on the render thread.

The census on the [Executable](game-executable.md) page came from a loaded image and a few lines of Python:

```python
import collections, re, sys

image = open(sys.argv[1], "rb").read()  # a loaded image, based at 0x82000000
names = set(re.findall(rb"\.\?A[VUW][A-Za-z0-9_@?$]{2,200}?@@", image))
namespaces = collections.Counter(
    n.decode()[4:-2].rsplit("@", 1)[-1] for n in names if b"@" in n[4:-2])
print(len(names), "types;", namespaces.most_common(10))
```

`pinyon_shift_fh1_archive_extract --xex-image` writes the loaded image from the user's own `default.xex`. Executable images and anything extracted from them stay local ([Legal](legal.md)).

### The generated code

The recompiler writes each guest function as `sub_XXXXXXXX` in the local `generated/` tree, with each guest instruction as a comment above its C++. To find who calls a function, or which functions read a field, search that tree:

```sh
# Callers of the time-of-day request function
rg -l "sub_825C7DD0\(ctx" generated/
# Functions that load from offset 10488 of an object (time_of_day.seconds)
rg -n "REX_LOAD_\w+\(ctx\.r\d+\.u32 \+ 10488\)" generated/
```

`tools/map-generated-lines.py` maps a line of generated code back to its guest address, which helps when a host profiler names a generated line rather than a guest function.

### A Ghidra workspace

For browsing call graphs and cross-references, `tools/re/ghidra-workspace.py` builds a Ghidra project in `.local/re/ghidra` from your own `default.xex`. It needs Ghidra 12.1.3, a JDK 21 and the XEXLoaderWV extension in `.local/re/tools` ([NL-2.2](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEXT_LEVEL_RESEARCH.md) lists the sources). The tool imports the executable headlessly and applies what the repository already knows: ShiftGlue's function starts, so Ghidra's functions match the generated `sub_` functions one for one, the recorded names (a "guess" stays a comment) and the vtables from `classes.json`. Analysis turns about 11,000 of the 76,885 starts into data, so the tool applies the table a second time after it. Ghidra's PowerPC language doesn't decode VMX128, so the generated C++ stays the reference for vector code. The project never leaves `.local`.

```sh
python -I tools/re/ghidra-workspace.py --generated .local/generated/default
```

### Data files

The game's data is in `media/`: ZIP archives, loose XML, a SQLite database and FMOD sound banks. Python's `zipfile` lists any archive, but most members use the Xbox LZX codec (method 21), so reading them takes the project's extractor:

```sh
# List an archive (names, sizes, methods)
python -c "import zipfile,sys; [print(i.compress_type, i.file_size, i.filename) for i in zipfile.ZipFile(sys.argv[1]).infolist()]" media/gamemodes.zip
# Extract one member, or all of them, into a private folder
pinyon_shift_fh1_archive_extract --archive-member media/gamemodes.zip game_free_roam_flow.xml out/flow.xml
pinyon_shift_fh1_archive_extract --archive-all media/gamemodes.zip out/gamemodes
# Read the database without changing it
sqlite3 "file:media/db/gamedb.slt?mode=ro" ".tables"
# Keys and text of a string table, for set_ui_string
python tools/fh1-strings.py --archive media/StringTables/EN.zip --table PauseMenu.str --grep resume
```

Matching names between data and code links the two. That is how the [Game flow](game-flow.md) page found that every behaviour in the flow scripts is a class in the executable.

## Probing the running game

### Mid-assembly hooks

A mid-assembly hook calls a host function at one guest instruction, with the guest registers it names. It is declared in `config/rexglue/analysis/main-xex.toml` and takes effect on the next code generation:

```toml
# The simulation step (f31) is final and about to be stored at owner+448.
[[midasm_hook]]
address = 0x823EDB84
name = "PinyonShiftObserveSimulationDelta"
registers = ["f31"]
```

```cpp
// src/pinyon_shift_runtime_hooks.cpp (shortened)
void PinyonShiftObserveSimulationDelta(PPCRegister& f31) {
  const double seconds = f31.f64;
  if (!std::isfinite(seconds) || seconds < 0.0 || seconds > 0.25) return;
  if (const double scale = pinyon_shift::cheats::TimeScale(); scale != 1.0) {
    f31.f64 = seconds * scale;  // the trainer's game speed
  }
}
```

A hook that only logs is the quickest experiment: the address and the register it reads are the hypothesis, and one run confirms or rejects it. The [Runtime](runtime.md#hooks) page explains how hooks are generated.

### Probe mods

A mod can read and write guest memory and call guest functions without a rebuild of the game. Functions and offsets come from the symbol table by name, so they resolve on the base game and v4 alike. This one logs the player's credits once a second, through symbols and offsets documented on [Game objects](game-objects.md). The symbol table holds functions and hook sites only, so the one global it needs is written out (v4 keeps it at `0x833CAAE4`):

```c
#include "pinyon_mod.h"
#include <stdio.h>

static const PinyonModApi* api;
static unsigned frames;

/* Guest memory is big-endian. */
static uint32_t load_u32(uint32_t address) {
  uint8_t b[4] = {0};
  if (api->read_guest(address, b, 4)) return 0;
  return (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3];
}

static void read_credits(void* unused) {
  (void)unused;
  /* The game object's address is held at 0x832DF024 in the base game. */
  uint32_t game = load_u32(0x832DF024);
  if (!game) return;
  uint32_t user = load_u32(game + (uint32_t)api->find_offset("game.user"));
  if (!user) return;
  uint32_t profile = api->call_guest(api->find_symbol("profile.from_user"), &user, 1);
  uint8_t loaded = 0;
  api->read_guest(profile + (uint32_t)api->find_offset("profile.loaded"), &loaded, 1);
  if (!profile || !loaded) return;  /* the career profile is not loaded yet */
  uint32_t credits = api->call_guest(api->find_symbol("profile.credits"), &profile, 1);
  char text[64];
  snprintf(text, sizeof text, "credits %u", credits);
  api->log(PINYON_LOG_INFO, text);
}

static void on_frame(void* user, const PinyonHookEvent* event) {
  (void)event;
  if (++frames % 60 == 0) api->enqueue_guest_task(read_credits, user);  /* call_guest needs a guest task */
}

PINYON_MOD_EXPORT uint32_t rex_mod_abi_version(void) { return PINYON_MOD_ABI_VERSION; }
PINYON_MOD_EXPORT int rex_mod_create(const PinyonModApi* host, PinyonMod* mod) {
  api = host;
  api->subscribe(PINYON_HOOK_FRAME_TICK, on_frame, NULL);
  mod->self = NULL;
  return 0;
}
```

Probe mods found the launch-option flags, the Treasure Map's reveal path and the car LOD tables; the [Modding](modding.md) page covers building and installing one. `PINYON_HOOK_FILE_OPEN` reports every file the game opens, which answers "is this file used?" in one run.

### Profilers

`pinyon_shift_thread_sampler` samples every guest thread and maps the samples to guest functions; on Android, `simpleperf record --call-graph fp` does the same with call chains. A function's share of a thread is often the first hint of what it is: the render thread's idle loop and the LZX decoder were both found this way ([Threads and frame loop](game-threads.md)).

`tools/subsystem-cpu.py` adds those samples up by subsystem (physics, scene submission, simulation, audio, crowd), from root functions listed in `config/performance/subsystems.toml` for both builds. A sample counts for the first group with a root on its stack. In a sustained desktop race, scene submission took 36 % of the guest CPU and physics 10 % ([Threads and frame loop](game-threads.md)).

### The probe build

A sampler sees where time goes; the probe build counts what happens. `PINYON_SHIFT_RECOMP_PROBE=ON` generates the game a second time into `.local/generated-probe` with a counter at every function entry and a per-thread record of every indirect call's target (`rex/ppc/probe.h`). When a scripted route completes, the runtime writes `logs/probe.json` into the run's state directory, and one script reads any number of them:

```powershell
python tools/re/probe-summary.py .local/runs/probe-race/state/logs/probe.json --generated .local/generated-probe/default
```

It lists functions by call count with the knowledge base's names, the functions no route entered, and each indirect call site with the number of distinct targets it reached. One race route answered three questions at once: half of the 76,257 functions are never entered during a race; two save/restore helpers make up 31 % of all calls; and 95 % of the 18,017 indirect call sites that ran reached exactly one target, so the game's virtual calls are mostly monomorphic in practice. The build is slower than the normal one (the counters are atomic), so the runner's `--no-performance-gate` flag keeps its timing from failing the route.

## Verifying

A finding that changes what the player sees is checked on a scripted route from a pinned save, so the run does not depend on how far the live save has progressed:

```powershell
python tools/create-render-seed.py free-roam-seed --state-root $stateRoot   # read-only snapshot of the save
python tools/run-fh1-render-test.py config/render-tests/fh1-free-roam.fh1test --state-root .local/render-seeds/free-roam-seed --output .local/runs/probe-on
```

The runner copies the seed into a private directory for each run, takes captures at fixed frames and reports the route's events. Two runs that differ in one cvar or one probe give an A/B pair; the car LOD and draw-distance records on [World and tracks](game-world.md) are such pairs, and most of them are negative.

On a phone, thermal drift makes two separate runs hard to compare, so a toggle is flipped every few hundred frames inside one run instead.

A change meant to keep behaviour rather than pixels, such as a native replacement of the car physics, is compared by how the cars drive. `--pinyon_shift_physics_trace=6` records every car's speed, engine, gear and controls, and `tools/physics-behaviour.py compare` checks the player's 0-100 km/h time, a race's or Rally stage's time, and the AI field's mean distance. Two runs of the same build are not identical: in a sustained race, single AI cars moved by up to 4 % and swapped places, while the 0-100 time held within 0.5 % and the AI's Rally stage time within 0.05 s. So the gates are those aggregates, at 2 % and 3 %, and single cars are only listed ([FH1_RENDER_TEST_AUTOMATION.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/FH1_RENDER_TEST_AUTOMATION.md#physics-behaviour-harness)).

## Mapping base addresses to the title update

The v4 title update moves almost every function. `tools/map-fh1-v4-addresses.py` pairs functions between the two loaded images and maps an address only when the match is unambiguous:

1. **exact**: the function's body is identical after masking branch targets and address-building immediates, and that body is unique in both images;
2. **aligned**: the function is reached through calls from exactly matched functions, and the address sits in a run of identical instructions;
3. **context**: a window of normalized instructions around the address occurs once in each image;
4. **data**: a data address built by the same `lis`/`addi` pair in matched code.

Anything else is reported as unmapped, never guessed. Field offsets are checked separately on aligned instructions whose base register is known to hold the object; one moved (`profile.loaded`, 40 to 44). The [Title update v4](game-title-update.md) page has the results.

```sh
python tools/map-fh1-v4-addresses.py base.bin v4.bin --addresses wanted.json --output mapped.json
```

## Recording a finding

Every finding goes into the repository in the same change that makes it:

- a semantic name a mod or hook uses: `config/mod/fh1-symbols.toml` (v4 offsets in `config/mod/fh1-offsets-v4.toml`), then `tools/generate-fh1-symbols.py`;
- everything else: a record in `site/findings/<topic>.toml`, which these pages render.

```toml
[[finding]]
group = "Time of day"                  # optional heading inside the page
base = "sub_825C7DD0"                  # base addresses, comma separated, or a file path
v4 = "sub_82656D40"                    # v4 equivalent, "same" for unchanged files, or empty
name = "time-of-day request"
what = """Moves the clock to a target time (`f1`, seconds) at a rate (`f2`, game seconds per second)."""
how = """Hook on the call; the trainer holds an hour with it."""
confidence = "confirmed"               # confirmed | probable | guess
note = ""                              # qualifies the confidence, optional
negative = false                       # true when the finding is that something does NOT work
issue = "#448"
source = "docs/NATIVE_PORT_BACKLOG.md NP-8.1"  # where the full reasoning is
```

`site/build.py` rejects a record with an unknown key, a missing name, an unknown confidence or a duplicate id, and the address index picks up every address in `base` automatically. `tools/re/kb.py` reads the same records as one address table: `lint` refuses text that reads like a disassembly listing or a hex dump ([Legal](legal.md)), `check` verifies that every `sub_XXXXXXXX` a record names is the start of a generated function (in the v4 tree too, when it exists), and `symbols` writes a JSON table whose `names` map labels `sub_` functions in profiles (`tools/summarize-thread-samples.py --symbols`). `tools/tests/test_re_kb.py` runs the lint and the check. Build and check the site:

```sh
.local/site-venv/Scripts/python site/build.py
```

Write only our own analysis: names, addresses, offsets, behaviour in our own words. No disassembly listings, decompiled code or game data.
