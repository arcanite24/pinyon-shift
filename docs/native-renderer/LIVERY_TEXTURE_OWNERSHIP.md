# Scaled texture binding ownership

Issue [#628](https://github.com/arcanite24/pinyon-shift/issues/628) reports world
texture corruption after saving decals or opening Design Creator with an
existing design. Entering the editor with a stock car clears it. The world
corruption reproduces at 2x on multivac with a private MX5 save containing three
white vinyl layers. The failure is a compressed texture selecting the scaled
buffer even though only part of its guest allocation still belongs to resolves.

## Mixed ownership of compressed textures

The old texture selection rule treated any resolved page in either the base or
mip range as sufficient to select the scaled buffer for the whole texture. The
livery path reuses physical memory also used by world assets. CPU writes return
part of that allocation to ordinary shared memory, while some mip or padding
pages retain old resolve ownership. Reloading a compressed world texture from
the scaled buffer then decodes unrelated render output as compressed blocks.

Two sampled DXT1 identities illustrate the transition: 768x256 textures at
transient physical bases `0E0DA000` and `0E095000`, with mip pages `E0F2` and
`E0AD`. Before the correction they remained scaled at payload generations 1 and
2. After it they use ordinary memory at both generations. These are per-run
allocation identities, not static guest symbols. Captures after painted-car
editor re-entry change from coloured noise on festival advertisements and black
road surfaces to intact logos and road textures.

Compressed textures now require every page of every stored base/mip range to
belong to resolves before selecting the scaled buffer. A fully resolved
compressed texture remains eligible. Uncompressed render targets keep their
partial-resolve handling. This changes source selection; it does not flush
texture contents or clear unrelated textures.

The regression models a 768x256 DXT1 allocation transitioning between full GPU
ownership, CPU base with old GPU mips, and GPU base with CPU mips. Against the
pre-correction cache it fails three of 27 assertions; the corrected cache passes
all 27, including the binding memo regression below. The full SDK suite passes
298 tests (four skipped), with 2,465 assertions.

### Partly resolved compressed targets

A review asked whether the complete-ownership rule could send a compressed
texture the GPU made itself, such as a livery, to stale ordinary memory when a
resolve covers only part of its base or mip range. On multivac (RTX 4080,
Windows Vulkan, v4 build, 2026-10-19) a temporary log in
`FindOrCreateTexture` recorded every compressed texture the rule rejected
although some page of it belonged to resolves. A route from the v4 reference
seed fast travels to Race Central, then runs the `fh1-livery-save` steps
(three white layers saved to the stock MX5) and re-enters Design Creator with
the painted car.

At 2x the edit-and-save run logged 46 distinct rejected textures and the
re-entry run 6. All but one had no resolved page in the base and leftover
resolve pages only in the mips, the stale-allocation case this rule exists
for. They include the same 768x256 DXT1 allocation as above, a 1024x1024
DXT5 and 64x64 DXT1 textures. The exception was one 8x8 DXT5 whose padded
16 KiB base was partly resolved, seen once during the return to free roam and
not in the re-entry run. The design on the door, the festival advertisements
and the road matched a 1x run of the edit-and-save route, and the re-entered
design and world were intact at 2x (the 1x re-entry run missed its map cursor
and was not compared). The rule stays as it is.

## The cache defect

The six fetch-constant words describe a guest texture. They do not say whether
its bytes currently belong to the ordinary shared-memory buffer or the scaled
resolve buffer. `FindOrCreateTexture` makes that choice from the resolve-page
map and includes `scaled_resolve` in the actual host texture key.

The binding memo stored the selected host texture pointer alongside the fetch
words. After a GPU resolve or CPU write, selective binding invalidation cleared
the affected binding, but retained the memo. Repeating the same fetch words
then recovered the old pointer without checking the current ownership map.
Consequently a CPU texture could keep reading the scaled buffer, or a resolved
texture could keep reading the ordinary buffer.

At scaled resolutions, a memo entry naming an outdated texture now goes
through `FindOrCreateTexture` again. Clean entries and the 1x path retain their
existing reuse. This does not flush texture contents, drop unrelated bindings,
or clear the whole cache per frame.

## Regression coverage

The SDK's `tests/unit/graphics/texture_cache_test.cpp` exercises the real shared
cache and memory watches with a backend that records no GPU commands. It keeps
the fetch constants unchanged while switching CPU → scaled resolve → CPU,
including consuming an invalidation while only another binding is requested.
It checks the selected host texture and verifies that an unrelated texture's
payload generation never changes.

On multivac (Windows x64, 2026-10-18), the standalone fixture fails two of its
14 assertions with the original cache: the resolved texture is still the
original unscaled object. With the patch all 14 assertions pass. The regression
also passes in the SDK unit suite built entirely from the worktree sources.

## Single-channel editor resolves

Entering Add Decals from a stock MX5 also exposed an unsupported native resolve:
`c0->t2/1x/s0`, followed by `c0->t2/4x/s6`, with destination register
`0x01000100`. These copy RGBA8 EDRAM into a tiled 8-bit unorm texture, including
the average of all four MSAA samples. The native planner rejected destination
format `k_8`, producing backend draw failures. This is an observed editor defect;
it alone does not explain corruption after saving a design.

The resolve shader now packs this format into one byte per texel, after sample
averaging, exponent bias, and channel swap. Atomic masked word updates preserve
the other three bytes while independent texel threads execute. Endianness
permutes the destination byte lane. The same tiled and scaled address formulas
apply with bytes-per-texel log2 set to zero. This path uses the ordinary texture
reload mechanism rather than the optional direct-to-32-bit-texture optimization.

Both DXBC and SPIR-V resolve variants were rebuilt using the SDK shader script's
compiler options. All 12 SPIR-V variants pass `spirv-val`. A unit regression
passes the observed destination register through the real resolve planner at
1x and 4x MSAA, checking support, byte size, destination extent, and base.

The first editor-entry ownership trace recorded 278,506 invalidation ranges,
of which 259,069 came from GPU writes, and 84 sampled texture reload attempts.
Four sampled identities had both ordinary and scaled host allocations, including
the 1280x720 front buffers. It contained no whole-512-MiB GPU invalidation.
Those observations establish alias activity, not which world texture becomes
corrupt after a saved design; that needs the acceptance checks below.

## Gameplay acceptance

The unit regression establishes the cache defects independently of menu timing.
The functional routes use a pinned private stock-MX5 save at Race Central with
the first-time design tips still enabled, then a second pinned snapshot of the
saved three-layer design. They never use a writable AppData or source seed.
The captures must show these actions, not merely a route result of `pass`:

1. Enter Paint Shop and Design Creator with a stock car, add decals, and save.
2. Exit to free roam; check the design, road surfaces, and roadside signs.
3. Travel away and return, then restart from a snapshot of the saved private
   state and check the same textures.
4. Re-enter Design Creator with the painted car and repeat the world checks.
5. Enter the editor with a stock car without adding a decal as a control.

Use `fh1_texture_reload_probe` to correlate texture allocation IDs, physical
base/mip ranges, scaled variants, and CPU/GPU invalidation reasons. A route
result marked `pass` proves that the script completed; its captures must also
show that it actually reached and saved in the editor.

`config/render-tests/fh1-livery-save.fh1test` selects a white shape, stamps three
layers, saves to the current car, accepts the Paint Shop exit confirmation,
and captures the world. `fh1-livery-reentry.fh1test` reloads that design, enters
Design Creator without editing, exits, and travels to Race Central. Both use
a 60 Hz wall clock with a 30 fps game cap for the short map-cursor pulse:

```powershell
python tools/run-fh1-render-test.py config/render-tests/fh1-livery-save.fh1test `
  --state-root .local/private-seeds/livery-stock --output .local/livery-save `
  --hidden --no-performance-gate `
  --game-argument=--resolution_scale=2 `
  --game-argument=--pinyon_shift_fh1_render_fps_limit=30
```

Pin the resulting private `.local/livery-save.state` directory before running
the re-entry route; it needs the three shader catalogs copied from the original
pinned seed into its `cache` directory. In a fleet worktree, use an explicit
private destination rather than writing through the shared `render-seeds`
junction:

```python
from pathlib import Path
import runpy
seed = runpy.run_path("tools/create-render-seed.py")["create_seed"]
seed(Path(".local/livery-save.state"), Path(".local/private-seeds/livery-painted"),
     "private saved three-layer design")
```

The fixture profile and generated livery data are private test inputs, not
repository artifacts.

Diagnostic exclusions retained the corrupted signs with draw reuse disabled,
selective binding reset disabled, row/layer reloads disabled, and direct
resolve-to-texture writes disabled. Disabling one-off readbacks retained the
sign corruption and also damaged the car, so those readbacks remain enabled.
That exclusion used a private diagnostic executor build: the retained
`fh1_native_readback_new_resolves` cvar is only consumed by legacy D3D12.

## Verified result

On multivac (RTX 4080, Windows Release, Vulkan, 2026-10-18), visual checks of
private per-run copies gave these results:

| Check | 1x | 2x |
| --- | --- | --- |
| Place three white layers and save to the current MX5 | Passed | Passed |
| Exit the shop and inspect road and festival advertisements | Passed | Passed |
| Restart from a pinned copy of that saved design | Passed | Passed |
| Re-enter Design Creator, exit, and travel to Race Central | Passed | Passed |
| Inspect the white door design and world textures after travel | Passed | Passed |
| Stock car: enter Add Decals and back out without adding a layer | Not run | Passed |

The complete-ownership correction restores the reproduced signs and roads;
the earlier memo and R8 corrections alone did not. The full tools suite passes
531 tests (nine skipped), with 100 subtests passed. The site builds 37 pages and
the new documentation links resolve.

The source-ownership range trace was collected at 2x. A 1x diagnostic run with
the startup range probe enabled timed out before its first capture (240 s);
the normal 1x boot, save, reload and travel checks passed with that probe off.
This diagnostic startup behavior needs separate investigation.
