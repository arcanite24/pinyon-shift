# What still assumes the Xbox 360: loading, streaming and console-era limits

Written 2026-11-16 at `dev` `b09f11bb` (SDK `cf2824ff`). The question:
which parts of the game and the runtime are still shaped by the Xbox 360's
hardware (a 12x DVD with slow seeks, 512 MB of shared memory, three cores
with six hardware threads, a fixed GPU, a console-paced system layer), and
which could be replaced so that boot, loads, fast travel and streaming
behave like a native PC or phone game on an SSD or NVMe drive?

The research (everything below Results) was written before anything was
built or run; [Results](#results-2026-11-16) holds what was measured. It combines a static census of the
game executable (strings, the launch-options object, the generated code),
a read of the ShiftGlue runtime, the existing research pages and a short
survey of other ports. Numbers marked *estimate* are arithmetic, not
measurements. The rule from [NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md#loading-times-on-modern-storage)
stands: **measure first.** Every row below names the probe that sizes it,
and no row may change defaults before CE-0 gives it a baseline.

Reverse-engineering results from this census are recorded in
`site/findings/` (systems, threads, flow, files); this page only cites them.

## Summary

- **Measured since ([Results](#results-2026-11-16)):** the console-era
  wait that mattered was the loading screen's minimum time on screen, not
  the disc. Clearing it saves 1.0 s into free roam and 2.9 s into and out
  of each race on multivac, and is the default now. The disc lock, the XAM
  sleeps, guest inflate, occlusion queries and scatter reads were measured
  and rejected or found moot. The bullets below are the research as
  written before measuring.
- **The disk is not the bottleneck, and the game knows it was.** A play
  session read 189 MB in 4,538 reads for 91 ms, and 1,203 opens took
  108 ms ([files](../site/findings/files.toml), "loading is guest work, not
  disk"). But the game still runs the machinery it built for a DVD: a
  disc lock that pauses its background streaming workers during foreground
  reads, a file cache with a fixed chunk size, a ZIP CRC switch, a
  `pausephysicsonstreaming` switch, and memory arenas sized at boot for
  512 MB. Each of these is a lever that costs nothing to try once its
  default and its cost are read at run time.
- **The runtime adds its own console-era waits.** Every deferred XAM
  completion (content create and open, overlapped enumeration, dialogs)
  sleeps a fixed 25 ms on one dispatch thread
  (`src/system/kernel_state.cpp:70`, `:1262`). Every guest occlusion-query
  end drains the whole Vulkan queue
  (`src/graphics/vulkan/command_processor.cpp:8264`), and the 528 query ends
  happen only in the title-to-free-roam load and the event menus. Both were
  measured nowhere because no load route exists.
- **Load time has never been measured by phase.** The 212-343 ms
  transition frames with 75-350 texture reloads are from a 2026-09-28
  session, before compute copies, AOT pipelines and the cache changes. CE-0
  (load-phase markers and a load route) comes before everything else.
- **What is already closed stays closed.** EDRAM, resolves, untiling,
  write-watch granularity, XMA, WMV decode, affinities, byte-swapped memory,
  a larger guest memory for the stock game and the 1 ms timestamp timer are
  measured and recorded in [lessons](../site/pages/lessons.md#what-didnt-pay-off-here)
  and the research pages listed at the end. None is re-proposed.
- **Other ports confirm the shape, not the numbers.** UnleashedRecomp
  removed a movie wait that the Xbox version used to stretch loads and says
  the remaining load stutters are work the game does not do asynchronously;
  FH1-ReImagined found cold pipelines and texture reloads, not file IO,
  in its FH1 loads. DirectStorage does not apply: our IO is 91 ms and our
  formats are LZX and deflate. Sources in [Outside evidence](#outside-evidence).

## Results (2026-11-16)

Measured on multivac (RTX 4080, Windows, Vulkan, base build, warm cache)
with one probe build: the counters of CE-0.4 in the ShiftGlue perf log,
`process_us` on the render-test wait and input events (CE-0.1), the
launch-option dump `pinyon_shift_console_option_census` (CE-0.3) and the
`ce-load` route, which syncs on Press Start, the car in free roam, the
car-select thumbnails and the race's replay stream from the
`appdata-2026-09-27` seed. Loads are timed from the button press to the
state the route waits for.

**The one big console-era wait was not the disc.** The tip loading screen
has a minimum time on screen: 1 s from the title screen to free roam, 3 s
into an event. The main thread yields until the renderer's deadline
passes, however early loading finished ([threads](../site/findings/threads.toml),
"loading screen minimum time"). Clearing the deadline as soon as it is set:

| Load | Console minimum | Cleared |
| --- | --- | --- |
| Title screen to free roam | 1.56 s | 0.55 s |
| Car select to race loaded | 4.62 s | 1.66 s |
| Retiring from a race to free roam | 4.22 s | 1.32 s |

Race captures after the load were pixel-identical, and the loading screen
still appears and fades. `pinyon_shift_loading_screen_minimum` (off by
default; base and v4) keeps the console behaviour. A second build with the
replacement in `src/guest_native/loading_screen.cpp` gave 0.51 s and 1.71 s
against 1.52 s and 4.65 s with the minimum kept. The exit is timed from
confirming the retire to the free-roam fade-in; there the game held a black
screen for most of the 3 s before its loading screen appeared. Fast travel
does not set the minimum. On the v4 build (seed `backport-1115-v4`) the same
route went from 1.70 s and 4.53 s to 0.73 s and 1.59 s.

Where the rest of a load goes (one run; boot is process start to Press
Start, 6.45 s):

| Counter | Boot | Title to free roam | Free roam to car select | Car select to race loaded | Whole route |
| --- | --- | --- | --- | --- | --- |
| File opens (ms) | 757 (106) | 209 (47) | 177 (41) | 210 (36) | 1,355 (230) |
| File reads (MB, ms) | 43, 18 | 59, 25 | 85, 43 | 37, 15 | 263, 122 |
| LZX, native (calls, ms) | 547, 29 | 1,643, 120 | 5,907, 404 | 2,522, 181 | 11,305, 776 |
| Deflate, guest (calls, ms) | 0 | 2, 0.2 | 46, 14 | 50, 13 | 98, 27 |
| Disc lock held (ms) | 129 | 102 | 35 | 22 | 299 |
| XAM sleeps (ms) | 0 | 151 | 0 | 0 | 151 |
| GPU allocations (count, ms) | 17, 1.8 | 44, 1.8 | 879, 11 | 5, 0.2 | 1,293, 18 |
| Texture loads (count, CPU ms) | 8, 11 | 3,126, 4 | 6,286, 16 | 1,377, 3 | 20,850, 60 |

During the title-to-free-roam load the main thread and the asset workers
spent 75-90 % of their time waiting (thread sampler), not computing: with
the minimum gone, what is left is the game's own sequential work.

| Row | Result |
| --- | --- |
| CE-0.1, 0.3, 0.4 | Done on multivac as above. The Deck and the Odin were not run: the one kept change is a wait that does not depend on the device |
| CE-0.2 | Warm runs only; a cold-cache run was not made. Reads are 122 ms of a whole route warm |
| CE-1 | Two deferred completions and one dialog close, 151 ms of sleeps. Setting `xam_deferred_completion_ms` and `xam_ui_close_delay_ms` to 0 moved Press Start and both loads by +0.09 s, within noise. Rejected; the delays stay as cvars at 25 and 100 ms |
| CE-2 | No host occlusion-query ends on Windows: host queries turn themselves off and the game reads emulated counts. Nothing to remove here |
| CE-3 | 1,355 opens in 230 ms (170 µs each) and 7,760 queries in 29 ms per route. At most 0.2 s per session; not pursued |
| CE-4 | No scatter reads. Dropped |
| CE-5 | Not measured cold; 88 % of reads are on asynchronous handles completed inline, 122 ms in all warm |
| CE-6 | 1,293 allocations, 18 ms per route. Not worth committing the mirror up front |
| CE-7 | 20,850 non-resolve texture loads, 60 ms of CPU per route. Not pursued |
| CE-8, CE-9 | Not run: in-place ISO reads are deferred, and STFS is install-time only |
| CE-10 | Held 299 ms per route. Skipping the bracket broke loading (car-select thumbnails never arrived). Rejected |
| CE-11 | Defaults read (systems, "memory arenas sized at boot"). `streamsize` at 1.5x (204 MiB), alone and with `d3dfixedsize` at 96 MiB, booted and raced normally but changed nothing: title to free roam 0.47-0.53 s and car select to race 1.67-1.75 s against 0.51 s and 1.67 s, the same slow transition frames, and texture reloads within run-to-run spread (the race's resolve reloads are host-side). Rejected |
| CE-12 | `filecachesize` 30 MiB, `filechunksize` 1 MiB, `checkzipcrc` already 0. A 4 MiB chunk (with `keepcarpartmemory` on) gave 0.44 s and 1.73 s against 0.51 s and 1.71 s: no change. Rejected |
| CE-13 | The flow-graph gates are the game's own; the fixed wait that mattered was the renderer's minimum above |
| CE-14 | `dvdsafe` has no reader (static). `keepcarpartmemory` on changed neither load into the race (above); with the 4 MiB chunk it retired to free roam in 1.30 s against 1.32 s. Rejected. `enablepvspredictahead` is already 1 and `pausephysicsonstreaming` 0, so nothing is held back by default |
| CE-15 | Guest deflate is 27 ms per route. NR-8 is not worth doing for loading |
| CE-16 | Not needed: decompression is 0.8 s per route, all of it native LZX |
| CE-17, CE-18 | Not loading; left to the audio research (NN-4.2, NR-6) |
| CE-19 | No guest delay was truncated to whole milliseconds in the route. Dropped |

## CE-0: measure loads first

| ID | Item | Done when |
| --- | --- | --- |
| CE-0.1 | **Load-phase markers** in the render-test JSONL and the critical-path trace: process start, title screen, title to free roam ready, event entry (menu confirm to countdown), event exit to free roam, fast travel. "Ready" is the first frame after the flow leaves `CWaitForStreaming` and the car can move. | A route prints each phase in ms on multivac, the Deck and the Odin |
| CE-0.2 | **A load route** (`fh1-load-cycle`): boot, free roam, one event entry and exit, two fast travels, from a pinned seed. Run warm and cold (Deck: `drop_caches`; Windows: a reboot or a cache-flush tool; Odin: the first run after a reboot, since `drop_caches` needs root). | Three warm and two cold baselines per device |
| CE-0.3 | **One-shot state dump at frame 1**: the default value of every launch option this page names (offsets below), the seven arena sizes from `sub_82482E70`, the streaming heap size from `sub_82482718`. | Values recorded in [systems](../site/findings/systems.toml), "memory arenas sized at boot" |
| CE-0.4 | **Counters, all in one probe build**: time inside the disc-lock bracket and the workers' blocked time; deferred XAM completions and their summed sleep; occlusion-query ends and await time; non-resolve texture loads with CPU time, bytes and render-pass splits; `vkAllocateMemory` and sparse binds with duration; `NtReadFileScatter` calls and bytes; opens split into unique, repeated and missing; `cache:` opens and writes. | One table per load phase, per device |

CE-0.4 is one build and one route matrix: every counter goes in at once,
so the devices run few, grouped routes, and the rows below are ranked
again by what it finds.

## Candidates

Effort: S is days, M a week or two. Payoff is per load unless stated.
Confidence is about the premise: confirmed in code, probable, or a guess.

### Runtime (ShiftGlue)

| ID | Candidate | What is 360-shaped now | Replacement | Probe and expected payoff | Effort, risk |
| --- | --- | --- | --- | --- | --- |
| CE-1 | **Fixed 25 ms deferred XAM completion** | `kDeferredOverlappedDelayMillis = 25` (`src/system/kernel_state.cpp:70`), slept inside every deferred completion (`:1262`), one at a time on a single dispatch thread (`:673-693`). Callers: content create and open (`xam_content.cpp:260`), overlapped enumeration (`xam_enum.cpp:66`), dialogs, which add 100 ms after completing (`xam_ui.cpp:96,154,196,220,243`). The delay imitates XAM reporting "pending" and finishing later; Xenia Canary chose 25 ms because 100 ms only lengthened boot | Complete on the next dispatch pass with no sleep, behind a cvar (`xam_deferred_completion_ms`, default 0 once measured) | CE-0.4 counts completions from boot to free roam and per save. If the 21 DLC packages and the profile go through it, about 0.5 s at boot plus 25 ms per save *estimate*. Confidence: confirmed in code, unknown use | S, low to medium: some titles race an instant completion; check boot, saves, DLC and the dirty-disc path |
| CE-2 | **Occlusion-query end drains the queue** | `EndGuestOcclusionQuery` ends the render pass, submits, then `AwaitAllQueueOperationsCompletion()` (`src/graphics/vulkan/command_processor.cpp:8238-8288`) before writing the sample count. On the console the GPU writes the count into guest memory and the title polls it. 1,056 `EVENT_WRITE_ZPD` events (about 528 query ends) all land in the title-to-free-roam load and the event menus ([rendering](../site/findings/rendering.toml)). A60-6 closed this as "not needed" because the race ends none; loads were never assessed | Copy the result into the readback buffer and write the guest report from the submission's fence callback; the title's own poll keeps the order | CE-0.4 times the await. 0.1-0.5 s per load at 0.2-1 ms a drain *estimate*, more on Android. A/B with `occlusion_query_enable=false` as an upper bound | S-M, low to medium: a result one submission later must still satisfy the poll |
| CE-3 | **Per-open and per-query host file costs** | Every open of a cached child calls `std::filesystem::exists` even on read-only devices (`virtual_file_system.cpp:274-283`); each open resolves the path twice and walks children linearly under `tree_mutex` (`:247-262`, `entry.cpp:53-66`); `NtQueryInformationFile(NetworkOpen)` stats the host file every time (`xboxkrnl_io_info.cpp:170`); `CreateFileW` gives no access hint (`filesystem_win.cpp:216`) | On read-only devices skip the existence check and the re-stat; a case-folded hash per directory; a small cache of open read-only handles per entry; `FILE_FLAG_SEQUENTIAL_SCAN` or `posix_fadvise` for archives | The open observer split from CE-0.4. 1,203 opens at about 90 µs each are 108 ms today; 50-100 ms per session on desktop *estimate*, more on Android storage | S, low |
| CE-4 | **`NtReadFileScatter` in 4 KiB host calls** | `XFile::ReadScatter` (`src/system/xfile.cpp:221-259`) issues one `ReadInternal` per 4,096-byte segment, each with its own lookup, syscall and, for physical memory, a `TriggerCallbacks` under the global critical region. Scatter-gather was the DVD DMA shape | Merge segments contiguous in guest memory into one read, else `ReadFileScatter`/`preadv`; one invalidation for the range | CE-0.4 counts calls and bytes; drop the item if the title never calls it | S, low |
| CE-5 | **Reads block the loading thread, and cold reads were never measured** | `if (true \|\| file->is_synchronous())` (`xboxkrnl_io.cpp:283`): every read finishes inline, and an asynchronous handle gets `X_STATUS_PENDING` with an event already set. The 91 ms figure is most likely a warm page cache | Keep guest semantics synchronous; read ahead the archive ranges a load touches on a host worker (`posix_fadvise(WILLNEED)`, `PrefetchVirtualMemory`, or a plain prefetching read) | CE-0.2 cold against warm. Matters on the Deck's microSD and Android storage, nothing on a warm desktop | S-M, low |
| CE-6 | **Device memory allocated during transitions** | The sparse guest-memory mirror commits each 4 MiB chunk on first touch with a synchronous `vkAllocateMemory` and bind on the commands thread (`vulkan/shared_memory.cpp:262-300`); texture memory is preallocated (256 MB) only on Android (`vulkan/texture_cache.cpp:74-85`). The console had 512 MB of fixed memory and nothing to allocate | On desktop and the Deck, commit the mirror at startup; a texture preallocation on Windows and Linux too | CE-0.4 allocation timeline over boot, load and event entry on the RTX 4080, the Deck and the UHD 620. Removes 5-30 ms stalls from first loads *estimate*; costs up to 512 MB of VRAM, or RAM on UMA devices | S, low: a small safe win if the stalls show up |
| CE-7 | **Transition texture loads run one by one** | Each load in `RequestRanges` (`src/graphics/shared_memory.cpp:520-672`) copies guest memory on the CPU (`vulkan/shared_memory.cpp:368`), may end the open rendering (`kGpuUploadSplitsTexture`, `:311-324`), then gets its own barriers and dispatch (`vulkan/texture_cache.cpp:2187+`). Only resolve-sourced reloads are timed (`pipeline/texture/cache.cpp:643-670`) | Gather a draw window's pending loads: one merged upload, one barrier batch, dispatches grouped by load shader, before the rendering opens; later a transfer or async-compute queue | CE-0.4 gives today's number in place of the September figure. Tens of ms per transition frame *estimate*; nothing in the race | M, medium: a guest write between the batch and the draw needs the keep-dirty logic |
| CE-8 | **Disc image read through page faults** | Reading the ISO in place maps the whole image (`disc_image_device.cpp:33`) and copies from the mapping (`disc_image_file.cpp:35`), so each first touch is a fault with no size hint (FUSE on Android). This is the deferred TP item "read the disc image in place" ([TIME_TO_PLAY_BACKLOG.md](TIME_TO_PLAY_BACKLOG.md)) | `pread` into guest memory, or `madvise` per read | Only if TP reopens in-place reads: time to free roam and major faults, ISO against extracted folder | S, low |
| CE-9 | **STFS reads scan the block list from the start** | `stfs_container_file.cpp:42-63` scans the block chain on every read and does an `fseek` and `fread` per 4 KiB block, sharing one `FILE*` per package without a lock. At run time DLC mounts as extracted folders (`content_manager.cpp:56-60`); the STFS device is used by `InstallContent` (`:682`) | An index of merged block runs and `pread` | DLC install time only | S, low |

### Game (guest code)

All addresses are base. The option offsets are into the launch-options
object at `0x832E29A0` ([systems](../site/findings/systems.toml), "launch-options object").
None of the defaults is known yet; CE-0.3 reads them.

| ID | Candidate | What is 360-shaped now | Replacement | Probe and expected payoff | Effort, risk |
| --- | --- | --- | --- | --- | --- |
| CE-10 | **The disc lock pauses background streaming** | 19 functions (mission flow XML, audio, track loading among them) take an `ExclusiveDiscIOLock` bracket, `sub_82E43888`/`sub_82E438B8`, which counts at asset-pool +1556 and resets the event at pool +112 that the streaming workers `82E4B2D0` and `82E4B3A0` wait on ([threads](../site/findings/threads.toml), "exclusive disc IO bracket"). On a DVD this stopped background reads from seeking the head away from a foreground load | Make the bracket a no-op so foreground and background reads overlap, if the count guards nothing else | CE-0.4 time held and workers' blocked time across a fast-travel and event-entry route. Medium for transition hitches. Confidence: probable | S, low to medium |
| CE-11 | **Streaming arenas fixed for 512 MB** | `sub_82482E70` sizes seven tracked physical regions at boot from `streamsize` (+2680), `d3dfixedsize` (+2712), `vehicleheapsize` (+2716), `nuiheapsize` (+2720), `compheapsize` (+2724) and `RingBufferSize` (+4284); `sub_82482718` sizes the streaming CPU heap from a value in Colorado's `.pvs` data times `streamfragmentationmultiple` (+2688), replaced by `overridestreamingcpuheapsize` (+2692) | Larger streaming and texture arenas through the options object, within the 512 MB guest physical space; whatever only the CPU reads could live outside it | CE-0.3 reads the sizes; then an A/B with the override doubled on the transition frames, counting reloads. Matters only if the reloads are guest evictions, not host cache invalidation (CE-0.4 tells which) | S probe, M change; medium: guest physical space is tight |
| CE-12 | **Guest file cache with a fixed chunk, ZIP CRC on** | `sub_82482E70` gives a `filecachesize` (+2700) physical buffer, `filechunksize` (+2704) and `checkzipcrc` (+2709) to the cache object `sub_82C600D8`. A chunked read cache hid DVD latency | Smaller cache (freeing guest physical memory for CE-11), larger chunks, CRC off for files already verified at setup | CE-0.3 values, then hit and miss counts and bytes copied per load. Low to medium | S, low for CRC and chunk size |
| CE-13 | **Streaming gates in the flow graphs** | `global.wait_for_streaming` appears four times in free roam, twice in festival races and once in fast travel, with `LoadAndWaitForLOD0Cars` and streaming switched off and on around loads ([flow](../site/findings/flow.toml), "loading waits in the flow graphs"). Fixed timers are almost absent: one half-second, one 2 s and one 3 s wait, three one-frame waits | No change until measured: the gate is correct, only its duration matters. The fixed waits can be shortened by a flow patch if they sit on a load path | CE-0.1 marks entry and exit of each `CWaitForStreaming` state; that is the load time the game itself sees | S probe |
| CE-14 | **Streaming and track switches** | `pausephysicsonstreaming` (+4868) is read in the simulation step `sub_823E3218` beside a per-car streaming byte at +1008 (*guess*: cars held while their area streams in); `preloadallmeshes` (+2739), `smalltexturesonly` (+2738) and `enablepvspredictahead` (+4264) are copied by `sub_825CEAD0` into the track-load parameters; `keepcarpartmemory` (+4566, `sub_8259C7D8`) and `WhenUnloadingDestroyTrack` (+8367, four readers) look like RAM-saving teardown | Predict-ahead on; keep car parts and the track between event and free roam if the defaults free them. `preloadallmeshes` cannot fit: Colorado's `bin.zip` is 2.9 GB | Count frames with the +1008 byte set on a fast drive; A/B predict-ahead on reload counts; A/B the two teardown switches on event exit to free roam | S each; medium for teardown (state left behind) |
| CE-15 | **Guest inflate during loading** | The deflate loop `sub_83108C08` is about 20 % of the asset worker while loading; LZX is native already. This is [NR-8](NATIVE_REPLACEMENT_RESEARCH.md) and stays there | A bit-exact native inflate, verified per call like LZX | Time to free roam with CE-0; tells NR-8 its real share | S, low |
| CE-16 | **Decompressed archives cached at setup** | Archives are PKZIP with LZX and deflate members, decompressed every run | Store decompressed members once (setup or first run) and serve them through the VFS, so the guest decompressor receives stored entries | Only if CE-0 shows decompression is a large share after CE-15; disk cost is the uncompressed size of the touched archives (not `bin.zip`'s 2.9 GB compressed) | M, medium: the guest must accept stored members, and the dirty-disc SHA table covers some files |

### Recorded and not pursued

- **`cache:` utility partition.** `sub_82518390` mounts it (through
  `sub_82C60498`, likely `XMountUtilityDrive`), compares a
  `game:\hash.manifest` that the disc does not ship, and can clear the cache
  keeping `$cache$`. The cache folder on multivac holds only replay and
  ghost streams, none of the 77 `FilesToCache.xml` copies, so the
  install-to-HDD copy does not appear to run. CE-0.4 confirms with a count
  of `cache:` writes; nothing to gain otherwise.
- **Disc-era options with no reader.** `dvdsafe` (+4194), `dvdsafecams`
  (+4195), `audiostreamsize`, `audioioblocksize` and `audioheapsize`
  (+3144/+3140/+3136) and `EnableLoadingAlarm` (+4560) are parsed, and a
  static scan of the getter's callers found no reader. `findzips`,
  `zipprioritybias` and `disabledirectoryhashtable` are read only at boot
  (`sub_824843E8`). Recorded so they are not chased again.
- **Dirty-disc SHA-256.** Already native (`XeCryptSha256*`) and covers about
  5.8 MB of core files, string tables and route XMLs.
- **Job threads pinned to six hardware threads.** `openmpnumthreads` and
  `openmpcpuids0-5` (+4224 onward) set the job pool; honouring affinities
  measured no gain, and the jobs are physics, not loading.

### Not loading, still console-shaped

| ID | Candidate | Now | Replacement | Probe | Effort, risk |
| --- | --- | --- | --- | --- | --- |
| CE-17 | **FMOD mixes 5.1 on stereo PCs** | `pinyon_shift_fmod_stereo` defaults on for Linux and Android only (`src/guest_native/fmod_stereo.cpp:26-31`); Windows and macOS mix six channels and fold them down | Pick stereo from the host device's channel count at init on every platform | The existing in-run A/B on multivac and blindvac; the Odin saved about 1 ms of mixer CPU a frame | S, low |
| CE-18 | **256-sample mix blocks** | FMOD mixes in 5.33 ms blocks, about 560 wakes a second of the mixer, the XAudio2 pass and the host audio worker ([audio](../site/findings/audio.toml)) | A larger FMOD DSP buffer set before init, now that the native output answers FMOD's voice | Mixer cycles per block idle against race, wake counts on the Deck (feeds NR-6) | S-M, medium: the Xenon output may assume 256 frames; adds about 16 ms of latency |
| CE-19 | **Guest sleeps in whole milliseconds** | `xthread.cpp:1353` truncates the delay to ms, and the non-alertable path uses `::Sleep`, accurate to 1 ms only because SDL3 calls `timeBeginPeriod(1)`; Windows 11 ignores that for hidden or occluded windows, so hidden runs get about 15.6 ms sleeps | Route every delay through the high-resolution `WaitUntil` (`threading_win.cpp:206`) | A histogram of delays by call site in the CE-0.4 build, plus one hidden-window audio run | S, low |

## Order

1. CE-0 (markers, load route, state dump, counters): one probe build, one
   route matrix on multivac, the Deck and the Odin.
2. The cheap runtime fixes the counters confirm: CE-1, CE-2, CE-3, CE-6,
   CE-4. Each is small and default-on once it passes the load route with
   identical world state.
3. The game switches by what CE-0.3 reads: CE-10, CE-12, CE-14, then the
   arenas (CE-11) only if reloads are guest evictions.
4. CE-7 and CE-15 if transition frames and decompression still lead.
5. CE-5 and CE-8 for cold storage (the Deck's microSD, Android); CE-16 last.
6. CE-17 to CE-19 can go into any build; they share no files with the rest.

Guardrails for every row: loads produce the same world state (cars,
position, time of day, event state) on `fh1-race-sync` and the load route;
base and v4 both pass; the AppData save is never written by a route.

## Outside evidence

- [UnleashedRecomp README](https://github.com/hedge-dev/UnleashedRecomp/blob/main/README.md):
  pipelines compiled from the asset-load path plus a fixed boot list; an
  option to skip the movie the Xbox version plays in full to lengthen
  loads; remaining load stutters attributed to work the game does not do
  asynchronously. Qualitative.
- FH1-ReImagined's [performance notes](https://github.com/FH1-ReImagined/ForzaHorizon1-ReImagined/blob/main/docs/perf.md),
  a separate FH1 project: a cold cache made 485 pipelines on the way into
  free roam (12 stutters, worst 500 ms) against 51 warm; about 88 texture
  loads a frame in free roam; long loading frames were the GPU front end
  waiting for guest commands.
- DirectStorage ports (Forspoken: 2.6 s on Win32 against 2.2 s with
  DirectStorage and CPU decompression): the gain is IO and GPU
  decompression, neither of which we are short of.
- No Xenia, Xenia Canary or RPCS3 patch for faster loads or larger streaming
  pools in a Forza title was found.

## Related pages

[NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md#loading-times-on-modern-storage) (the earlier loading plan this page expands),
[NATIVE_REPLACEMENT_RESEARCH.md](NATIVE_REPLACEMENT_RESEARCH.md),
[NEAR_NATIVE_RESEARCH.md](NEAR_NATIVE_RESEARCH.md),
[TIME_TO_PLAY_BACKLOG.md](TIME_TO_PLAY_BACKLOG.md),
[ANDROID_60FPS_BACKLOG.md](ANDROID_60FPS_BACKLOG.md) (A60-6),
[RECOMP_OPTIMIZATION_SURVEY.md](RECOMP_OPTIMIZATION_SURVEY.md).
