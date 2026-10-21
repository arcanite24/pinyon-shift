# Desktop frame inspector

On desktop Vulkan, **Ctrl+F8** opens the ImGui frame inspector. It is off
by default; `--fh1_frame_inspector=true` opens it at startup. **Capture next
frame** starts at the next swap and freezes the following complete frame.
Closing the panel discards its CPU snapshot and UI textures. It does not
pause or write the player's save.

The surface table shows the EDRAM base and pitch in tiles, host size, guest
format number, host sample count and draws issued to that surface during the
captured frame. Surfaces remain in the executor's cache across frames, so a
surface with zero draws can contain an earlier frame's contents. The preview
shows the image at the captured swap. Depth is shown as grayscale guest depth.

Resolve sources are captured before the resolve clears its input. A resolve
spanning several EDRAM owners has an entry for each source rectangle, with
the destination address and byte extent. These previews show source sample
zero **before destination format conversion, packing, endian conversion and
sample selection**; they are not decoded destination textures. Surface and
resolve previews use nearest sampling, preserve aspect ratio, clamp RGB to
0..1, and have at most 256 pixels on their longest side. Alpha is displayed
opaque. Capture is limited to 128 resolve sources, 256 previews and 512
texture identities; omissions and individual preview failures are visible.
If the resolve reinterprets another EDRAM layout, select the source surface:
the resolve row reports that alias rather than showing incorrectly mapped pixels.

Hover a row on **Texture hashes** to see the XXH3 hash of its CPU-authoritative
guest base-level bytes, the same byte domain used by texture replacement
filenames. GPU-written ranges, missing base levels and levels above 16 MiB
are reported as unavailable. Each texture key is recorded at its first
observed binding in the captured frame. A hash does not make a format eligible for a
texture pack: the replacement system's format and layout rules still apply.

## Opening a dump

Use a separate launch in which the title remains suspended:

```text
--fh1_frame_inspector_replay=true
```

Paste the local `.fh1frame` path and choose **Open dump**. To open one at
startup, also pass `--fh1_frame_replay=<path>`. This workspace forces inline
GPU recording and synchronous pipeline compilation, independent of player
settings. It reuses the normal dump replay implementation and compares the
replayed front buffer with the recording. The result appears in the panel
and in the usual `.replay.json` / `.replay.bin` files beside the dump. Opening
another dump first waits for GPU work and resets executor surfaces and EDRAM
ownership, texture and geometry caches, register memos and constant bindings.
Dump counts and byte ranges are bounded before allocation.
The suspended workspace repaints the host UI independently of guest swaps,
including one paint to erase a closed overlay. ImGui mouse and modifier inputs
are queued so a press and release between slow capture repaints is retained.

Wireframe is available only with Vulkan `fillModeNonSolid`. Overdraw needs
independent attachment blending; each attachment is also checked for blend
support before a diagnostic pipeline is used. The overdraw view replaces
fragment output with additive red (1/32 per fragment), disables depth and
stencil tests, and retains the frame's render-pass clears and color masks.
It is per-surface coverage between clears, not a count of shaded invocations
across the entire frame. Unsupported attachment formats keep their normal
pipeline. These diagnostic views are offered only in the suspended replay
workspace, keeping the running title's rendering state intact.

Select the view before **Open dump**; changing the radio button does not
replay automatically. Diagnostic output is expected to differ from the
recording. Compare **Color** for a meaningful front-buffer match.
For a scripted startup, `--fh1_frame_inspector_view=0|1|2` selects Color,
Wireframe or Overdraw before the initial dump is replayed.

For recording, seed isolation and command-line regression replay, see
[FH1_RENDER_TEST_AUTOMATION.md](FH1_RENDER_TEST_AUTOMATION.md#frame-dumps-and-offline-replay).
Frame dumps contain game data and belong under `.local`; never commit or
distribute them.

## Ownership and disabled cost

`Fh1FrameInspector` is one mailbox per command processor. Its request flag
is checked at swaps; draw counts and texture enumeration run only during a
requested capture. There are no inspection image copies, allocations,
texture hashes or GPU waits during ordinary rendering. Capturing intentionally
stalls once for GPU completion and may take much longer than a normal frame.

The executor's `Fh1FrameInspection` contains CPU RGBA arrays and values only.
The optional graphics-system inspection methods require GPU plugin ABI 3;
the runtime and GPU plugin must be rebuilt together.
All preview dispatches are queued on the GPU command thread, followed by
shader-write to host-read barriers, a completion wait and mapped-memory
invalidation. Readback buffers are freed after that wait. No live image,
descriptor, mapped pointer or executor surface is handed to the UI. The UI
owns its `ImmediateTexture` uploads until the snapshot changes or the panel
closes; the Vulkan immediate drawer retires GPU resources after their last
UI submission. A generation number rejects publication from a capture that
was closed while in flight.
Preview pipelines and descriptor layouts are created lazily and retained by
the executor until it is destroyed; replay replaces that executor between dumps.

For scripted verification, `cvar <script-frame> fh1_inspector_capture true`
arms the same one-shot capture and resets the cvar. The GPU log records counts
and XXH3 checksums of surface previews. To align a live snapshot with a dump,
arm that cvar and `fh1_frame_dump_frame -1` at the same route frame with
`gpu_record_thread=false` and 1x resolution. Cvar steps may share a script
frame and are applied in listed order. Replaying in Color should retain
the recording's front-buffer comparison; stale cached surfaces are not
required to match surfaces used by the recorded frame.

`config/render-tests/fh1-frame-inspector.fh1test` arms both requests after
the opening menu flow. Run it through `tools/run-fh1-render-test.py` with a
pinned seed, `--include-opening-movies`, and these game arguments:

```text
--game-argument=--gpu_backend=vulkan
--game-argument=--gpu_record_thread=false
--game-argument=--draw_resolution_scale_x=1
--game-argument=--draw_resolution_scale_y=1
--game-argument=--fh1_frame_dump_path=<absolute-local-path.fh1frame>
```

Then open the dump in the inspector workspace or use
`tools/replay-fh1-frame.py` for the front-buffer comparison.

## Windows qualification

On an RTX 4080, Windows Release, driver 581.08, a 1x pinned-seed opening-menu
route captured 34 cached surfaces, 95 resolve sources and 512 texture identities
(the texture limit). Replaying its dump captured 23 used surfaces and the same
95 resolve sources. Color inspection, plain replay, and Color reloaded after
an invalid dump produced identical replay bytes. Wireframe, overdraw, texture
hash hover, path editing, invalid-dump recovery and close/reopen were checked
in the desktop UI. Vulkan synchronization validation reported no errors;
the renderer's shader-output-not-consumed warnings were still present.

That recording did **not** match live output exactly: 50,133 of 942,080 words
differed in both plain and inspected Color replay. The inspector preserves the
normal replay result; it does not make every live frame replay-exact. Keep a
plain replay golden when testing renderer changes. Linux and macOS inspection
have not been qualified on hardware.

Disabled cost remains inconclusive. Against a private build with only the
inspection hooks removed, a 20-second parked window measured median 8.623 ms
for the control and 9.392 ms with inspection disabled (p95 10.912 and 11.468 ms).
To reduce guest-state variation, the same dump was then replayed 3,600 times
per process with synchronous compilation, measuring the interval from frame
600 to 3,600. In control/disabled/disabled/control order, average times were
9.974 / 10.434 / 10.493 / 11.435 ms per frame. Both build slots and the desktop
run lock were reserved. The varying control prevents a no-regression claim;
repeat the comparison under stable timing conditions before closing that
acceptance criterion. These are frame-execution measurements, not UI capture
latency; the inspection capture itself deliberately waits for the GPU.
