# GitHub issue fix backlog

Triaged 2026-10-04 against release **0.4.0**, host `c6b1f7e`, SDK
`0038a40`. Public checklist:
[#354](https://github.com/arcanite24/pinyon-shift/issues/354).

All 33 initially open issues were read, including their comments. The attached
diagnostic ZIPs, setup reports, launcher log and relevant setup screenshot were
inspected. These are triage findings and pending work, not newly implemented
fixes. Original attachments remain in their issue threads; local research is
under ignored `.local/issue-triage/2026-10-04/`.

Updated 2026-10-05 (Mexico City): reviewed all 16 subsequent issues,
[#355–#370](https://github.com/arcanite24/pinyon-shift/issues?q=is%3Aissue+sort%3Acreated-desc),
their comments, seven crash ZIPs and #362's setup report. Follow-up evidence
is under ignored `.local/issue-triage/2026-10-05/`. Reports timestamped
2026-10-06 UTC still fall on October 5 locally. The original disposition
below remains a historical snapshot; this update changes no issue states.

## Queue

### Live refresh, 2026-10-06

The first October 6 read-only inventory contains 27 open issues. Local receipts are
under `.local/issue-triage/open-issues-2026-10-06.json`; issue states were not
changed. Two new reports were read:

- [#372](https://github.com/arcanite24/pinyon-shift/issues/372) joins GH-1:
  LLVM 20 with the MSVC 2019 standard library cannot resolve C++23
  `std::byteswap`. Validate the selected standard library, not just the
  compiler version. Both attachments were inspected and confirm failures in
  multiple translation units at `rex/types.h:44`. An old-MSVC reproduction
  is still pending. Discovery now requires VS 2022 Build Tools 17.1 or newer,
  excluding VS 2019 so provisioning can install the supported tools. The
  version-selection regression and 35 release-contract tests pass; the
  selected local LLVM/MSVC environment also compiles a constexpr
  `std::byteswap` probe. Broader SDK capability checks remain open.
  The requirement follows the
  [Microsoft STL changelog](https://github.com/microsoft/STL/wiki/VS-2022-Changelog#vs-2022-171).
- [#371](https://github.com/arcanite24/pinyon-shift/issues/371) reports an
  access violation on an RTX 5060 without reproduction steps. Its inspected
  ZIP records a guest read of `0x03104884`, guest LR `0x82C6DFAC`, on clean
  host `c6b1f7e` / SDK `0038a40`. This is guest execution evidence, not proof
  of a GPU driver defect. Resolve that caller and reproduce the operation
  before grouping it with another crash. Local attachment receipts are in
  `E:/horizon1-recomp-tests/issue-371-20261006/` and `issue-372-20261006/`.

The subsequent read-only refresh still contains 27 open issues. A new
comment and setup report on #365 confirm VS 2022 is detected but its batch
parser exits 255 on `\data\temp\dd_vsdevcmd17_preinit_env.log`. The portable
install has parentheses in its TEMP path. The same failure reproduces with
local VS 2022 even with debug logging disabled: VsDevCmd expands TEMP
unquoted inside a batch block before its condition is evaluated. Setup now
uses a safe CommonApplicationData temporary directory for this child and
preserves the caller's TEMP/TMP on success and failure. The real local
initialization and all 36 release-contract tests pass. This fixes that
reproduced parser failure; the reporter's complete setup is not qualified.
Receipts: `.local/issue-triage/issue-365-setup-error-latest.json` and
`issue-365-temp-fix-verification.json`. No issue state was changed.

GH-14 remains historical D3D12 evidence. D3D12 is now a legacy backend;
current player support and new qualification use Vulkan. A Vulkan
reproduction is needed before treating #370 as a current renderer defect.

The native-menu follow-up refresh contains **28 open issues**. New
[#373](https://github.com/arcanite24/pinyon-shift/issues/373) reports a crash
during the first race after changing name/language, enabling the trainer and
damaging the car. Its attached report confirms clean release 0.4.0
(`c6b1f7e`, executable SHA-256 `D0D16984...7A4F106`) and a guest read at
`0x04D04888`, LR `0x82C222F0`, on an RTX 3050 Laptop / Ryzen 4800H system.
The caller is the continuation of a virtual call in `82C222C8`; register
evidence also includes `ctr=8240A848`, a pointer-validation path. This does
not establish the failing callee or a damage/trainer root cause. Reproduce
the named first-race flow from a private early-game save and compare trainer
and damage settings before changing code. No blanket pointer guard or GPU
workaround is justified by this report. The report has no shared memory dump.
Receipts: `.local/issue-triage/open-issues-20261006-native-model.json`,
`issue-373-20261006.json` and
`D:/horizon1-recomp-tests/github-373-20261006/report.zip`. No issue was posted
to or changed.

The consumer-filter refresh still contains 28 open issues, with no new IDs or
updated reports compared with that native-menu inventory. Receipt:
`.local/issue-triage/open-issues-20261006-consumer-filter.json`. The local native
UI experiment now passes pause close after removing redundant host page checks
from unrelated fread operations; visual focus remains open. This is not a
qualified fix for one of the reported GitHub defects.

The menu-stability refresh still contains **28 open issues**, with no new IDs
or updated reports. Receipt:
`.local/issue-triage/open-issues-20261006-menu-stability.json`. The subsequent
animation-reference fix qualifies the prototype's eighth-row focus and native
Difficulty activation/cancellation. This remains local UI work; original Rally
entry, Android graphics/performance and the reported crash reproductions are
unfinished. No public issue was posted to, closed or claimed fixed by this work.

The lifetime follow-up still contains 28 open issues and no new or updated
reports (`.local/issue-triage/open-issues-20261006-ui-lifetime.json`). Native
pause-button and owner/model cleanup now pass targeted private tests; this is
not a reproduced fix for a public crash report.

The menu-API refresh still contains 28 open issues with no new or updated
reports (`.local/issue-triage/open-issues-20261006-menu-api.json`). The local UI
API now rejects generation reuse after scene close. Release host checks also
execute their assertions rather than compiling those operations out; all eleven
runnable checks pass. These local fixes do not establish a root cause for any
of the reported guest crashes, and no issue state was changed.

The queue below retains earlier evidence and historical closed reports.
No new GitHub issue fix is claimed by this refresh.

The native Rally entry refresh contains the same 28 open issues with no new or
updated reports (`.local/issue-triage/open-issues-20261006-native-entry.json`).
The private native pause entry now reaches the seven-ticket Rally hub and
returns through Back, including a second activation after reopening pause.
The existing F6 route still reaches a moving Rally stage. These checks do not
qualify the original Rally flow or establish a fix for a reported public crash.
No issue state was changed.

The native car-selection refresh also contains 28 open issues with no changed
reports (`.local/issue-triage/open-issues-20261006-native-car-selection.json`).
The private native pause/Rally hub now opens the car chooser, supports cancel
and reopen, and confirms a car into the saved Red Rock fourth stage. Its timer,
race HUD, player driving and unchanged earned ledger pass targeted checks.
The private hub heading now reads HORIZON RALLY. Blank thumbnails, ticket
labels, prizes, eligibility and the production original flow remain open;
these checks do not establish a public crash fix.

P1 blocks installation, launch or progression; P2 covers rendering correctness,
performance, diagnosis and regression coverage; P3 covers requested features,
usability and mitigated effects. Effort is an estimate:
S = a few days, M = roughly one to two weeks, L = several weeks. Hardware and
reproduction availability can change the order.

| Order | ID | Priority | Work | Reports | Effort | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GH-1 | P1 | Validate toolchain capabilities and initialize the selected build environment | [#350](https://github.com/arcanite24/pinyon-shift/issues/350), [#339](https://github.com/arcanite24/pinyon-shift/issues/339), [#365](https://github.com/arcanite24/pinyon-shift/issues/365) | S–M | Header failures and a distinct VsDevCmd failure |
| 2 | GH-2 | P1 | Detect and repair incomplete source installs | [#347](https://github.com/arcanite24/pinyon-shift/issues/347) | S | Multiple required source files absent |
| 3 | GH-3 | P1 | Recover rejected configuration | [#345](https://github.com/arcanite24/pinyon-shift/issues/345), [#364](https://github.com/arcanite24/pinyon-shift/issues/364) | S | Two current-session schema rejections |
| 4 | GH-4 | P1 | Load imported Xenia saves safely | [#335](https://github.com/arcanite24/pinyon-shift/issues/335), [#353](https://github.com/arcanite24/pinyon-shift/issues/353) | M | Reproduction through 0.4.0 |
| 5 | GH-5 | P1 | Fix Viper-to-Corrado transition crashes | [#343](https://github.com/arcanite24/pinyon-shift/issues/343), [#327](https://github.com/arcanite24/pinyon-shift/issues/327) | M | Two different fault signatures |
| 6 | GH-6 | P1 | Qualify the remaining AMD Vulkan driver crash | [#352](https://github.com/arcanite24/pinyon-shift/issues/352) | M | Driver-module fault on 0.4.0 |
| 7 | GH-13 | P1 | Preserve setup errors and verify manifest/SDK compatibility | [#362](https://github.com/arcanite24/pinyon-shift/issues/362) | S–M | Closed report; manifest error masked by null Lines |
| 8 | GH-11 | P1 | Reproduce PR-stunt and driving guest dispatch crashes | [#359](https://github.com/arcanite24/pinyon-shift/issues/359), [#368](https://github.com/arcanite24/pinyon-shift/issues/368), [#366](https://github.com/arcanite24/pinyon-shift/issues/366) | M | Shared/nearby guest LR; distinct failure modes |
| 9 | GH-12 | P1 | Reproduce event-start null read | [#367](https://github.com/arcanite24/pinyon-shift/issues/367) | M | Guest read 0x44; event identity missing |
| 10 | GH-14 | P1 | Diagnose D3D12 device removal on GTX 1650 SUPER | [#370](https://github.com/arcanite24/pinyon-shift/issues/370) | M | Present fails with device removal/reset |
| 11 | GH-7 | P2 | Tie diagnostic tails and backend identity to the failed session | [#345](https://github.com/arcanite24/pinyon-shift/issues/345), [#351](https://github.com/arcanite24/pinyon-shift/issues/351), [#364](https://github.com/arcanite24/pinyon-shift/issues/364), [#357](https://github.com/arcanite24/pinyon-shift/issues/357) | S | Stale runtime tail; contradictory backend identity |
| 12 | GH-15 | P2 | Obtain missing Intel HD 620 startup diagnostics | [#361](https://github.com/arcanite24/pinyon-shift/issues/361) | S | Exit code only; no attachment or last action |
| 13 | GH-8 | P2 | Repair intro checkpoint resume without a route | [#319](https://github.com/arcanite24/pinyon-shift/issues/319) | M | Previously reproduced related limitation |
| 14 | GH-16 | P2 | Qualify AMD scene, exposure and photo-mode rendering | [#363](https://github.com/arcanite24/pinyon-shift/issues/363) | M–L | Multiple separately reported visual defects |
| 15 | GH-17 | P2 | Correct ultrawide map, menus and opponent labels | [#363](https://github.com/arcanite24/pinyon-shift/issues/363) | M | 21:9 clipping, stretching and label movement |
| 16 | GH-18 | P2 | Measure low-end PC performance and Vulkan flicker | [#369](https://github.com/arcanite24/pinyon-shift/issues/369), [#363](https://github.com/arcanite24/pinyon-shift/issues/363) | M | Reported 10–19 FPS and stalls; runtime measurements needed |
| 17 | GH-19 | P3 | Accept a validated extracted game directory | [#358](https://github.com/arcanite24/pinyon-shift/issues/358) | M | Requested alternative to ISO input |
| 18 | GH-20 | P3 | Verify language selection and make it discoverable | [#360](https://github.com/arcanite24/pinyon-shift/issues/360) | S | Reporter acknowledges existing Profile → Language option |
| 19 | GH-21 | P3 | Repair optional depth-of-field rendering | [#355](https://github.com/arcanite24/pinyon-shift/issues/355), [#356](https://github.com/arcanite24/pinyon-shift/issues/356), [#363](https://github.com/arcanite24/pinyon-shift/issues/363) | M | Disabling effect clears artifacts; default mitigation on dev |
| 20 | GH-9 | P3 | Qualify one racing wheel through existing input | [#337](https://github.com/arcanite24/pinyon-shift/issues/337) | M | Feature request; device needed |
| 21 | GH-10 | P3 | Complete the existing macOS port plan | [#310](https://github.com/arcanite24/pinyon-shift/issues/310) | L | Existing NP-13 plan; no qualified release |

GH-1 leads because one shared preflight can address two known installation
failures. GH-2 and GH-3 have bounded recovery paths. GH-4 and GH-5 need isolated
reproductions before any save-format or guest-lifetime change. GH-6 requires
affected hardware; an available Radeon tester can advance it earlier.
New crash work follows these bounded installation/configuration fixes. Visual
and low-end qualification should feed the existing renderer/performance plans;
it does not displace Linux, v4/DLC and easier Android builds already underway.

## Work and acceptance gates

### GH-1: toolchain capabilities

- **Evidence:** #350 fails at `rex/types.h` because `std::byteswap` is absent;
  #339 fails at `d3d12_provider.cpp` because
  `D3D12_FEATURE_DATA_D3D12_OPTIONS8` and
  `D3D12_FEATURE_D3D12_OPTIONS8` are absent. Switching the runtime graphics
  API cannot resolve these compile failures.
- **Starting point:** [release-common.ps1](tools/release-common.ps1),
  [provision-toolchain.ps1](tools/provision-toolchain.ps1),
  [install-build-tools.ps1](tools/install-build-tools.ps1) and
  [release-toolchain.json](config/release-toolchain.json). The shared Visual
  Studio lookup checks a component's presence, not whether the chosen headers
  satisfy the build.
- **Next change:** probe the selected library/SDK capabilities before the SDK
  build and report a precise supported update path. Gather the reporters'
  toolset/SDK versions; avoid guessing minimum versions or replacing standard
  library functions just to accommodate unidentified old headers.
- **Done when:** an old/incomplete environment fails early with the real
  requirement; a supported environment reaches the code-generator and game
  build. Extend the existing setup-failure checks with the smallest capability
  regression case. #45 and #212 are consolidated under the same reporter's
  newer, actionable #339; their original causes were not proven.

### GH-2: incomplete source installs

- **Evidence:** #347's CMake report cannot find `src/main.cpp` and several
  UI, config and save sources. The release include list already contains
  `src`, so absence in this user's tree does not prove the release omitted it.
- **Starting point:** `ResolveRepositoryRootAsync` in
  [MainWindow.xaml.cs](launcher/PinyonShift.Launcher/MainWindow.xaml.cs) and
  [package-launcher.ps1](tools/package-launcher.ps1). Root detection currently
  trusts just `config/supported-dumps.json` and `tools/setup-preview.ps1`;
  extraction is skipped when those markers and the recorded payload hash pass.
- **Next change:** reproduce a partial extraction/root and validate required
  sources before accepting it. Re-extract the existing verified payload when
  appropriate; distinguish a real development checkout from an extracted tree.
- **Done when:** a missing required source is detected before CMake and repaired
  or precisely reported. A complete payload still configures; user/config/save
  hashes are unchanged by repair. Extend existing release/payload checks.

### GH-3: unsupported configuration

- **Evidence:** #345's current session ends with `config.unsupported`,
  required schema 27. Exit 1306 (`0x51A`) is the deliberate configuration
  failure exit in [pinyon_shift_app.cpp](src/pinyon_shift_app.cpp). The bundled
  runtime tail belongs to an earlier successful Vulkan session. This is not
  sufficient evidence of a D3D12 driver failure.
- **Starting point:** `EnsureSupportedConfig`, the launcher settings path,
  [host-config.ps1](tools/host-config.ps1) and
  [set-graphics-experiment.ps1](tools/set-graphics-experiment.ps1). Obtain the
  reporter's host TOML with personal paths redacted.
- **Next change:** reproduce settings apply/restore and schema parsing; retain
  a backup and expose a recovery path for an invalid or unwritable TOML.
  Recovery is limited to host settings and must preserve the save tree.
- **Done when:** Vulkan → D3D12 → Vulkan changes survive restart with supported
  and migrated configs; malformed/future-schema configs are explained and
  recoverable. Reuse [test_graphics_settings.py](tools/tests/test_graphics_settings.py)
  and [test_host_config.py](tools/tests/test_host_config.py).

### GH-4: imported saves

- **Evidence:** #335 reproduces on 0.3.1; #353 confirms it on 0.4.0.
  Both stop with `0x80000003` while loading imported save data, then reach
  `XamShowMessageBoxUI` at caller `82A6EBF0`. #353 reports that restoring its
  native-save backup works again. This identifies the flow, not yet the cause.
- **Starting point:** the save load/decryption hooks in
  [pinyon_shift_runtime_hooks.cpp](src/pinyon_shift_runtime_hooks.cpp),
  [profile_body.cpp](src/save/profile_body.cpp), SDK content/profile identity,
  and [xam_dialogs.cpp](src/ui/xam_dialogs.cpp). Reports include sample saves;
  inspect them only as private copies.
- **Next change:** trace container, identity, decryption and validation failure,
  then the error-dialog path. Determine compatibility before promising import
  or proposing a conversion tool.
- **Done when:** a compatible imported save loads and survives save/reload;
  incompatible data produces a usable error without a breakpoint/crash or
  mutation of the input. Native progress and payloads stay intact.
  #335 remains canonical; #353 is closed as a duplicate with its evidence linked.

### GH-5: opening transition

- **Evidence:** #343 on 0.4.0 writes guest `0x2F`, LR `82E48984`.
  #327 on 0.3.0 calls a null indirect target, LR `82C2231C`.
  Both identify the Viper-to-Corrado transition. Keep distinct reports until
  lifetime tracing proves a shared root cause. The 0.4.0 pipeline-compilation
  rendering fix does not establish that either guest fault is resolved.
- **Starting point:** guest cleanup/module transitions, relevant runtime hooks
  and [fh1-opening-sync.fh1test](config/render-tests/fh1-opening-sync.fh1test).
- **Done when:** isolated cold/warm opening runs complete the transition on
  both APIs, with save/reload and timing checks. Add the smallest reproduction
  route or focused check that catches the identified root cause.

### GH-6: AMD qualification

- **Evidence:** #352 on 0.4.0 reads target `0x40` in
  `amdvlk64.dll+0x921529` on an R7 350. This is a different signature from
  the pre-0.4.0 submission-fence failure.
- **Next step:** collect the driver version and last action; compare D3D12,
  reproduce with Vulkan validation on affected hardware, and separate device
  capability, application validation and driver causes.
- **Done when:** the affected flow completes on the reported hardware/driver,
  or unsupported capabilities fail early with an accurate message. Do not
  infer the root cause merely from the driver being the faulting module.
  The earlier Radeon reports were closed against the shipped fence fix;
  affected-hardware confirmation of that fix is still welcome.

### GH-7: diagnostic session integrity

- **Evidence:** #345's session JSONL identifies the failed process while its
  runtime tail describes an earlier session. Startup can fail before runtime
  logging begins. #351 has no captured exception or reproducible last action;
  the termination cause is unknown.
- **Starting point:** [create-crash-report.ps1](tools/create-crash-report.ps1).
  It reads a fixed runtime-log tail without checking session identity, and
  its settings allowlist omits `gpu_backend`.
- **Done when:** a pre-logging failure cannot bundle a prior runtime/perf tail
  as evidence of the failed process. Report the selected API/device/driver
  through a small sanitized allowlist when available. A fixture with an old
  runtime log and new session must catch the mismatch. Preserve exclusions
  for game files, generated source, save data and memory dumps.

### GH-8: intro resume

The maintainer's earlier #319 investigation reproduced relaunching between
the end of the intro and the first festival event without a route; the
reported indefinite hang itself was not reproduced. Keep this known
regression in #354 even though #319 is closed pending hang diagnostics.
Reproduce each checkpoint boundary with isolated seed copies, repair the
progress/route transition, and gate quit/relaunch, next-event entry and
preservation of earned progress.

### GH-9: wheel input

#337 remains a feature request. The existing SDK SDL path opens gamepads and
implements gamepad rumble. Start with one real wheel's name/USB IDs, steering
and pedal axes, dead zones, disconnect/reconnect and menu input. Reuse that
path before adding a separate input backend. Acceptance requires usable
driving and unchanged controller behavior. Force feedback is separate work
requiring device qualification.

### GH-10: macOS

#310 remains open. Follow
[NP-13](docs/NATIVE_PORT_BACKLOG.md#np-13-macos): Apple Silicon build and
Mach-O thunk correctness, guest/save/route parity, MoltenVK validation and
packaging. Existing Android ARM64/Vulkan work is a prerequisite to reuse,
not proof of a Mac release. Acceptance is a documented disc-to-play flow on
a real Mac with the route and save/load gates.

## October 5 additions and follow-up evidence

### Existing work: GH-1, GH-3, GH-5, GH-6 and GH-7

- **#365 → GH-1:** setup finds Visual Studio but `VsDevCmd.bat` exits 255;
  the log mentions `dd_vsdevcmd17_preinit_env.log` under a path with spaces.
  Keep environment initialization distinct from #339/#350's header failures.
  Check command quoting, TEMP/TMP handling and the chosen installation with
  paths containing spaces. Done when a supported installation initializes
  or reports the actual failing command rather than simply claiming tools
  are absent. The quoted log does not prove outdated MSVC is the cause.
- **#364 → GH-3 and GH-7:** its 0.4.0 session records `config.unsupported`
  (schema 27), exit `0x51A`; the runtime tail is from a prior process that
  shut down normally. #345's reporter also confirms deleting the host TOML
  restored launch. Recovery helps, but the settings/schema failure remains
  pending a reproduction and a safe migration/recovery check.
- **#357 → GH-6 historical qualification and GH-7:** the ZIP identifies
  **0.3.1**, host `264fade`, SDK `4de586b`; Vulkan fence/submission errors
  precede exit `0xC0000409`. Obtain a current-build reproduction before
  treating it as another remaining 0.4.0 Radeon crash. The session's
  `logging.ready` says `d3d12` while runtime operations are Vulkan: include
  accurate requested and actual API identities in the diagnostic gate.
- **#366 ↔ GH-5:** the new driving crash has the same null indirect target
  and LR `82C2231C` as #327, but follows minutes of tailing a Drivatar rather
  than the intro transition. GH-11 tracks that additional flow; matching
  signatures alone do not establish one cause.

### GH-11: PR-stunt and driving dispatch crashes

#359 identifies the failed Ferrari F50 GT speed-trap result screen.
Its 0.4.0 snapshot reads guest `06204888`, LR `82C222F0`, CTR `8240A848`.
#368 reads `07E04888` with the same LR/CTR, but gives no reproduction steps.
#366 stops at a null indirect target, LR `82C2231C`, on a different driving
flow. Trace callback/object lifetime and dispatch at those sites, keeping
three reproductions until a shared cause is demonstrated. Obtain #368's last
action and relevant event identities. Done when failed/successful stunt
results, retry/return to driving and a prolonged Drivatar-follow route pass
from private seeds, with a regression check for the identified cause.

### GH-12: event-start null read

#367 reports starting an unnamed event. Its 0.4.0 crash reads guest `0x44`,
LR `82F9F238`, native offset `0x1391899`. The runtime tail also contains
failed relative `AMB_FA_Autoshow.fsb` opens; their proximity is not proof
of an audio/VFS cause. Identify the event and API, trace the failing object
and separately inspect those opens. Done when event entry, exit and re-entry
pass from an isolated checkpoint and the same guest fault no longer occurs.
Do not consolidate with GH-11 merely because both involve events.

### GH-13: manifest rejection and masked setup errors

#362 is already closed. Its log first reports that
`pinyon_shift_manifest.toml` has no `[project]` section, then the failure
reporter itself rejects null `Lines`. The attached setup JSON confirms
`New-PinyonCommandFailure` on Windows PowerShell 5.1. Check the installed
manifest against the pinned SDK's accepted format and preserve the original
code-generation error even when the captured log is empty. Include Unicode
user paths in the reproduction; mojibake alone does not prove the root cause.
Done when empty-output failures retain command/exit/context and a supported
manifest reaches code generation on that setup. Verify any intervening fix
before removing this gate; closure alone does not provide that evidence.

### GH-14: D3D12 device removal

#370's 0.4.0 report ends with `D3D12 present failed`, HRESULT `0x887A0005`
and removal reason `0x887A0007`, after repeated backend draw failures.
The process exits `0xC0000409` without a captured exception. Collect driver,
last action and actual settings, then compare APIs and inspect D3D12
validation/device-removal breadcrumbs. Done when the affected startup/scene
passes on GTX 1650 SUPER, or a reproducible unsupported capability is
reported accurately. Do not merge it into the AMD Vulkan item.

### GH-15: Intel startup report awaiting evidence

#361 supplies Intel HD Graphics 620, Windows build 19045 and exit
`0xC0000409`, but no ZIP, exception or failing action. Obtain the generated
diagnostic report, selected API, driver and point of termination before
assigning a runtime fix or declaring the GPU unsupported. Completion of
this triage item means an actionable reproduction or a supported explanation;
any resulting defect still needs its own behavior gate.

### GH-16: AMD rendering qualification

#363 reports RX 9060 XT / Adrenalin 26.8.1 at 2x, with missing rocks/floor
on a first run, temporary overbrightness, absent cutscene people and nearby
race crowds/barriers, missing Autoshow textures, a changing bottom-edge line
and broken car lights in photo mode. Keep these as separate checks in
[the renderer backlog](docs/DESKTOP_RENDERER_BACKLOG.md). Compare cold/warm
caches, APIs and 1x/2x before attributing them to shader preparation or
culling. Done when each scene has an affected-hardware capture and either a
qualified fix or a separate actionable defect. The reporter says the boxy
Vulkan shadows are now fixed for them; retain that as confirmation to qualify,
not another pending shadow defect. Depth of field is tracked in GH-21.

### GH-17: ultrawide UI and projection

#363 separately reports zoomed-map and post-quit title-screen corruption
outside 16:9, stretched Autoshow UI, and stretched/moving opponent names
at 2560×1080. It also requests one ultrawide preset instead of independently
choosing Stretched and Wider view. Qualify each screen at 16:9 and 21:9,
then add a preset using existing settings if appropriate. Done when map
zoom/pan, menu return, Autoshow and world labels remain correctly placed
without regressing the standard aspect ratio.

### GH-18: low-end performance and streaming stalls

#369 reports roughly 17 FPS on Intel Xe / i3-1115G4, plus black/white Vulkan
flicker; a comment reports 15–19 FPS, dropping to 10, on Vega 7 / Ryzen 5
5500U. These are user observations, not controlled benchmarks. #363 also
reports periodic stutters with stopped sound and slow area loading. Add
affected devices to [PB-0](docs/PERFORMANCE_BACKLOG.md#pb-0-measure-and-instrument):
record API/driver, selected adapter, resolution, power mode, RAM, cold/warm
cache and the same route's CPU/GPU times and frame-time percentiles.
Track Intel flicker as a separate correctness reproduction. Done when a
measured bottleneck has a before/after route comparison on affected hardware
and the chosen preset's fidelity is qualified; promise no FPS floor yet.
Reuse the streaming/multicore roadmap work rather than opening another
optimization program.

### GH-19: validated extracted-folder input

#358 requests choosing a personally extracted supported game folder in the
launcher and CLI to avoid retaining/recreating an ISO. Plan a required-file
hash manifest derived locally from a verified supported disc; validating
only `default.xex` is insufficient to establish full asset compatibility.
Reuse the existing setup stages after validation. Done when matching input
builds through both entry points, modified/incomplete/unsupported folders
fail early with useful errors, and the source tree remains unchanged.
No game files belong in release artifacts or the repository.

### GH-20: language discovery

#360's comments identify the existing Options → Profile → Language setting,
and the requester acknowledges finding it. Treat this as verification and
discoverability work, not evidence that native language support is absent.
Check the option's availability during early progression and its restart
behavior, and keep documentation aligned with the current settings UI.
Done when a fresh supported install can find, select and retain a disc
language across restart. This is distinct from launcher/host UI translation.

### GH-21: optional depth of field

#355 (closed), #356 and #363 all link cutscene artifacts to depth of field;
#356's RX 7600 / Adrenalin 26.9.2 reporter confirms disabling it restores
normal cutscenes. [512b0e6](https://github.com/arcanite24/pinyon-shift/commit/512b0e6)
disables depth of field and motion blur by default on dev, preserving explicit
user choices. This mitigates the effect and does not repair its rendering.
Keep the optional effect fix at lower priority. Done when enabled/disabled
captures of affected cutscenes are correct on qualified APIs/GPUs and a
fresh configuration retains the safe defaults. These reports establish
depth-of-field artifacts, not a reproduced motion-blur defect.

## Original October 4 triage disposition

| Result | Count | Issues | Reason |
| --- | ---: | --- | --- |
| Closed: shipped fix | 5 | [#321](https://github.com/arcanite24/pinyon-shift/issues/321), [#326](https://github.com/arcanite24/pinyon-shift/issues/326), [#331](https://github.com/arcanite24/pinyon-shift/issues/331), [#336](https://github.com/arcanite24/pinyon-shift/issues/336), [#333](https://github.com/arcanite24/pinyon-shift/issues/333) | Four pre-0.4.0 Vulkan fence failures; one exact Treasure Map null-read match |
| Closed: consolidated | 3 | [#45](https://github.com/arcanite24/pinyon-shift/issues/45), [#212](https://github.com/arcanite24/pinyon-shift/issues/212), [#353](https://github.com/arcanite24/pinyon-shift/issues/353) | Older build reports → #339; imported-save duplicate → #335 |
| Closed: needs information | 13 | [#62](https://github.com/arcanite24/pinyon-shift/issues/62), [#121](https://github.com/arcanite24/pinyon-shift/issues/121), [#224](https://github.com/arcanite24/pinyon-shift/issues/224), [#319](https://github.com/arcanite24/pinyon-shift/issues/319), [#329](https://github.com/arcanite24/pinyon-shift/issues/329), [#332](https://github.com/arcanite24/pinyon-shift/issues/332), [#334](https://github.com/arcanite24/pinyon-shift/issues/334), [#338](https://github.com/arcanite24/pinyon-shift/issues/338), [#341](https://github.com/arcanite24/pinyon-shift/issues/341), [#344](https://github.com/arcanite24/pinyon-shift/issues/344), [#346](https://github.com/arcanite24/pinyon-shift/issues/346), [#348](https://github.com/arcanite24/pinyon-shift/issues/348), [#351](https://github.com/arcanite24/pinyon-shift/issues/351) | Missing diagnostics, underlying error, current measurements or identifiable failing flow |
| Closed: expected rejection | 1 | [#342](https://github.com/arcanite24/pinyon-shift/issues/342) | Disc failed exact supported size/hash verification |
| Closed: out of scope | 1 | [#349](https://github.com/arcanite24/pinyon-shift/issues/349) | Promotional invitation |
| Kept open | 10 | [#310](https://github.com/arcanite24/pinyon-shift/issues/310), [#327](https://github.com/arcanite24/pinyon-shift/issues/327), [#335](https://github.com/arcanite24/pinyon-shift/issues/335), [#337](https://github.com/arcanite24/pinyon-shift/issues/337), [#339](https://github.com/arcanite24/pinyon-shift/issues/339), [#343](https://github.com/arcanite24/pinyon-shift/issues/343), [#345](https://github.com/arcanite24/pinyon-shift/issues/345), [#347](https://github.com/arcanite24/pinyon-shift/issues/347), [#350](https://github.com/arcanite24/pinyon-shift/issues/350), [#352](https://github.com/arcanite24/pinyon-shift/issues/352) | Actionable failures or requested feature/platform work |

Each issue received a rationale and a link to #354. Missing-information
closures are **unresolved**, use GitHub's `not_planned` closure reason with
the `question` label, and specify the evidence needed to reopen.
Duplicates retain their original evidence. No conversation was locked.

The #333 diagnostic matches the already-fixed #330 fault offset
`0x512ECB3`, guest address `0x38` and return address `828BCA64`.
[c9562a2](https://github.com/arcanite24/pinyon-shift/commit/c9562a2)
guards both collectibles callers. The Radeon fence fix is
[fd97e4d](https://github.com/arcanite24/pinyon-shift/commit/fd97e4d).
Both ship in [0.4.0](docs/releases/0.4.0.md); neither closure claims fresh
qualification on the reporters' PCs.

## Validation policy

Check a backlog item only after its affected behavior and a meaningful
regression check pass. Keep a current reproducible defect open until then.
Use the existing tests/routes before creating a new harness.

All scripted gameplay follows [AGENTS.md](AGENTS.md): take a read-only seed
with [create-render-seed.py](tools/create-render-seed.py), and run
[run-fh1-render-test.py](tools/run-fh1-render-test.py) with that seed as
`--state-root`. The runner owns a private copy. Never move, reset or
overwrite the AppData save or an imported sample's original copy.

The original pass checked coverage of 33 reports and final GitHub states/labels.
The October 5 update checks coverage of all 16 additions, unique queue IDs,
repository links and the saved public checklist. It changes backlog content
only; the pending fixes have not been built or tested.


The owned-native-menu follow-up read-only inventory still contains **28 open
issues**, with no changed IDs or update timestamps from the preceding native
car-selection inventory. Receipt:
`.local/issue-triage/open-issues-20261006-owned-native-menu.json`.
The new optional Rally preparation and scoped menu/cancellation qualification
do not reproduce or resolve a public crash report. No issue state or comment
was changed. Physical Rally entry and Android qualification remain open.


## Issue-focused goal, 2026-10-06

The maintainer now authorizes focused fix commits and closing verified completed
issues. Rally/Android work remains intact; issue work is the current priority.
The live queue has 27 open issues after completing #365.

- [x] #365: commit `37dcef2` (`fix(setup): isolate vsdevcmd temporary paths`)
  isolates the child TEMP/TMP used by VsDevCmd and restores caller paths on
  success/failure. The exact staged regression passes, including child exit
  preservation; real VS 2022 initialization with parenthesized caller paths
  passes. GitHub closure is verified as COMPLETED. The closure explicitly says
  the commit is local, not pushed or released. It does not claim reporter-wide
  installation qualification or completion of GH-1's separate header probes.
- [ ] Continue GH-1's actual C++ library/SDK capability probes (#350/#339/#372),
  then source installation repair, configuration recovery and progression
  blockers. Keep hardware-dependent or unresolved reports open.

Receipt: `.local/issue-triage/issue-goal-start-20261006.json`. Prior statements
about unchanged issue states above are historical. Only the two setup files
and the relevant regression were committed; unrelated worktree changes remain.


### Selected toolchain capabilities, 2026-10-06

Commit `ea6ac88` requires VS 2022 Build Tools 17.1 or newer and probes the actual
selected C++ library (`std::byteswap`) and Windows SDK (`D3D12_OPTIONS8`) before
building. Compiler output, exit codes and component-specific update instructions
reach the existing setup-error reporting path. The real toolchain and deliberate
incompatible library/SDK header fixtures pass their positive/negative checks,
including Unicode/parenthesized temporary paths and cleanup. All 37 contract/probe
checks and three exact-staged-file checks pass.

#350 and #372 are closed as COMPLETED with validation and unreleased/local commit
status stated in each closure. #339 remains open: its SDK update/selection recovery
and successful rebuild need qualification. GH-1 in public checklist #354 remains
unchecked and now records these partial completions and the remaining gate.
There are 25 open issues. No commits were pushed or releases published. Unrelated
Rally/Android work remains uncommitted and preserved.

Receipts: `.local/issue-triage/open-issues-after-capability-fix-20261006.json` and
`354-capability-update.md`. Closure verification reports COMPLETED for both issues.


### Source installation repair, 2026-10-06

Local commit `bb6f759` fixes #347 and public GH-2. Exact staged WPF launcher checks restore missing main/config/UI/save sources, replace truncated source, reject incomplete payloads without marking them installed, distinguish managed installations from checkouts, and preserve save bytes, settings and unrelated files. Existing folder/portable/graphics/layout checks pass. #347 is verified CLOSED/COMPLETED; GH-2 is checked in #354. No commit was pushed or released. Original AppData saves and unrelated Rally/Android changes are preserved.


### Crash-session integrity, 2026-10-06

Local commit `ab872dd` matches diagnostics to PID/UTC start and session-bound crash/performance files, omits runtime before logging, filters appended runtime by start time, and separates requested settings from initialized backend. All 37 contract/session checks and two exact staged checks pass. Isolated replays of the original #345/#364 bundles preserve failed configuration events and omit their stale successful runtime tails. These configuration failures remain open; original TOMLs are unavailable. GH-7 remains unchecked for selected-device instrumentation/qualification. No push or release. Saves and input diagnostic bundles preserved.


### Empty codegen failure reporting, 2026-10-06

Local commit `bdf3da5` fixes reproduced null Lines binding for missing/empty logs and captures codegen console errors before native logging. Twenty setup-report checks and six exact staged checks pass. Real pinned CLI ASCII-path probes retain missing project diagnostics and accept valid manifest layout before rejecting the intentionally missing entrypoint. Cyrillic log-path probe exits 0xC0000409 before console output; this is retained in `.local/issue-triage/gh13-unicode-native-failure.json` and needs a native path fix. GH-13 remains unchecked for Unicode recovery and successful full translation. No issue newly closed and no push/release. Original data and unrelated work preserved.


### Unicode code generation qualified, 2026-10-06

Local commit `dba2c21` embeds a UTF-8 process manifest in the locally built pinned CLI and captures UTF-8 diagnostics with caller encoding restored. This supersedes the Cyrillic-path failure recorded in the preceding entry. All 57 setup/contract checks and two exact staged checks pass; native CLI invalid/valid manifest probes pass on ASCII and mixed Cyrillic/Chinese paths, with repeatable manifest merges. Full private code generation from copies of default/SpeechFacade/XMediaFacade finishes in 84 seconds, writes 675 generated files (681 total output files), and passes native warning verification. Original executable hashes are unchanged; no save is accessed. GH-13 in #354 is checked complete, with bdf3da5 retaining absent-log and early-console errors. #362 was already closed. No new issue closure, push or release. Receipt: `.local/issue-triage/gh13-full-unicode-codegen.json`; private artifacts `D:/horizon1-recomp-tests/codegen-unicode-20261006`.


### Opening-crash reproduction route, 2026-10-06

Local commit `801adc8` repairs startup synchronization in the opening route (recent file-open acceptance and longer bounded waits for movie wall time). All 58 runner checks pass. The exact staged route captures moving Viper gameplay on Vulkan; the extended 23,000-frame private probe completes without the reported signatures but stops off-road in the Viper and never reaches Corrado. This is a reproduction prerequisite, not a transition fix. #343/#327 remain open and GH-5 unchecked. Current generated base-disc instructions distinguish a critical-section queue/vector append (#343) from parent/child virtual teardown (#327); no shared cause proven. Cold/warm native transition and save/reload qualification remain required on supported Vulkan. Prior both-API wording is superseded by Vulkan-only support; Direct3D 12 is legacy. The pinned AppData seed profile hash is unchanged. No push or release. Receipts: `.local/issue-triage/gh5-opening-qualification-20261006.json` and `gh5-native-call-paths-20261006.md`.

### Imported-save validation reproduced, 2026-10-06

The supplied #335 save reproduces 0x80000003 on the current Vulkan build in a private per-run state (session 20261006T183026Z-p40268). Native frames map to the title's save-validation failure callback and fatal dispatcher; the encrypted body is read but decryption is never reached. The initial fixture omitted the source Headers tree, so metadata-preserving import remains a required comparison. Limited offline signing-key candidates did not match; corruption, identity mismatch, and hash implementation defects are not yet distinguished. #335/GH-4 remain open; no bypass or product fix claimed. Live saves and pinned seeds untouched. Receipt: .local/issue-triage/gh4-import-validation-20261006.md.

### Selected Vulkan device diagnostics qualified, 2026-10-06

Local commit `1fa7194` completes GH-7 with the preceding session-tail fix `ab872dd`. The actual initialized Vulkan provider records the selected device name, vendor/device IDs, API version and raw driver version. The Windows report binds it to the failed PID/session and displays it in the issue draft. Requested backend stays separate; old/early logs without selected-device evidence report actual backend unknown. All 37 contract/session checks and two exact staged checks pass. A private native-save run reaches game mode 17 with two captures; the actual imported-save crash bundle identifies RTX 4080 and excludes private snapshot payloads. Pinned seed profile SHA-256 unchanged. GH-7 in #354 is checked; #345/#364 and #351/#357 remain open for their separate root causes. No push/release. Receipt: .local/issue-triage/gh7-selected-gpu-20261006.json.

### Imported-save metadata and positive-control comparison, 2026-10-06

The original #335 Headers tree is now included in a private seed and still produces the same fatal save-validation path (session 20261006T183849Z-p20572). A native pinned save matches the exact title-derived HMAC-SHA256 key for the default SDK identity and key index 0; both supplied #335/#353 sample profiles fail the limited candidate-identity probe. This validates the probe's native positive control but does not distinguish other source identities, other title keys, corruption, or the guest-selected input. The decoded base binary is already mapped in virtual memory layout; applying ordinary raw-PE section translation was incorrect. Temporary generated instrumentation was overwritten by normal codegen and the current generated source equals the saved original; no probe remains. Native positive gameplay loads successfully. #335/GH-4 remain open. No AppData save was written.


### Extracted game source support completed, 2026-10-06

Local commit `97b7968` adds the launcher folder picker/drop support and setup `-ExtractedPath` (`-GamePath`/`-GameDir`) input. An exact-ISO-derived 2,400-file catalog verifies full contents before copying to the build cache, preserves the source, rejects incomplete/modified/extra/linked files and overlapping source/destination paths, and skips the system-update directory. Source folders do not claim ISO whole-file hash verification. 37 contract/source checks, exact staged WPF and setup checks, complete fresh/existing tree verification, packaged ZIP contents and 920-pixel setup layout pass. Isolated orchestration mocks expensive provisioning/build stages; actual launcher compilation succeeds. Packaging now builds in its artifacts directory to avoid the already open launcher executable lock. #358 is verified CLOSED/COMPLETED and GH-19 in #354 checked complete. No push/release; unrelated Rally/Android changes and live saves preserved. Private extraction: D:/horizon1-recomp-tests/gh19-extracted-catalog-20261006.


### UTF-8 BOM startup rejection fixed, 2026-10-06

Local commit `3e3c96d` normalizes the UTF-8 BOM through the shared host reader and uses that reader at the startup schema gate. The actual pre-fix gate rejects current/older schema keys on a BOM-prefixed first line; after the fix, valid current files load unchanged, supported old files migrate with original-byte backups, and unsupported/missing schema files still reject unchanged. 58 startup/configuration/contract checks and three exact staged gate checks pass. Native build and two private gameplay runs pass; the fresh-backup run (20261006T191944Z-p23956) retains exactly the BOM seed config bytes and reaches game mode 17. Pinned profile hash unchanged. GH-3 updated but unchecked; #345/#364 remain open because their original TOMLs are unavailable. Receipt: .local/issue-triage/gh3-config-bom-qualification-20261006.json. No push/release.

### New report #374 triaged, 2026-10-06

New open report has exit 0xCFFFFFFF, Windows 19045, RTX 2060 SUPER plus spacedesk adapter, no exception, no reproduction details, no diagnostic attachment and no comments. It is unclassified; adapter enumeration does not establish the selected GPU or a graphics root cause. Keep open until diagnostic/reproduction evidence exists; no speculative fix or duplicate closure. Queue refresh currently includes this report.

### Shared child dispatch and event output-handle triage, 2026-10-06

Original #359/#368/#373 bundles match the child method load at guest 82C22310 after the parent virtual method returns, with three different low patterned vtables. LR/CTR are stale from completed calls: CTR 8240A848 does not prove a fault inside the allocator. #367 instead reloads a null output handle and reads handle+68 at 82F9F338. Nearby sound-file failures do not establish its cause. No root fix or closure; trace object/output-slot ownership in reproducing private routes. Receipt: .local/issue-triage/gh11-gh12-call-paths-20261006.md.

### Language discovery qualified, 2026-10-06

Local documentation commit `0696578` adds F6 → Profile → Language, Left/Right and restart instructions. Private fresh-profile run 20261006T192803Z-p42792 reaches Profile before gameplay and saves Mexican Spanish; fresh process 20261006T192922Z-p34132 shows PRESIONA START and retains language 5/country 71. Existing feature, no new language implementation. #360 verified CLOSED/COMPLETED and GH-20 checked in #354. Pinned profile hash unchanged; live saves untouched. No push/release. Receipt: .local/issue-triage/gh20-language-qualification-20261006.json.

### Child ownership probe and actual Gauntlet entry, 2026-10-06

Local commit `16ead1a` adds opt-in read-only before/after-parent child snapshots and a wall-time Gauntlet route with a race HUD assertion. Native build and exact staged probe checks pass (disabled/no reads, nested pairs, register preservation, invalid/overflowing pointer handling). First output-frame boundary run never entered the event; captures show early inputs ignored, so it does not qualify retirement. Corrected private entry reaches event/car/start menus; extended driving run 20261006T193933Z-p14840 reaches native race mode 3 at 126 mph, with 8,317 pairs across five threads and no child/vtable changes. Default-off staged route 20261006T194233Z-p42652 also reaches driving, passes HUD assertion and emits no trace events. Native control parents 82D7ABE0/82DF10C8 use child vtable 822496A4; its method 82448FD8 releases refcount at child+32. This does not establish the original lifetime violation. All crashes remain open; no push/release; pinned profile hash unchanged and live saves untouched. Receipt: .local/issue-triage/gh11-child-dispatch-qualification-20261006.json.

### New #375/#376 reports, 2026-10-06

#375 reports unspecified gameplay/customization visual glitches on 0.4.0, RTX 2060, Ryzen 3600, with no logs or scenes; remains unqualified. #376 supplies a ZIP and tutorial-end crash that succeeds on retry. Guest 82C22310 reads child vtable 08C0487C+12, matching the shared dispatch pattern; parent AC65D568, child 2EA154D0, LR82C222F0, stale CTR8240A848. Its cutscene artifacts at Vulkan 2x (DoF/motion blur enabled) and European-disc/Polish-audio request are separate scopes; no source dump or screenshots qualified locally. Both remain open. Fresh queue: 25 open issues. Original bundles retained unchanged.


### Completed-work checkpoint published, 2026-10-06

The twelve completed issue-work commits through `16ead1a` and checkpoint
`fac2230` are now pushed to `origin/dev`; no release was published. This
supersedes the earlier local/not-pushed status statements. The checkpoint is
`docs/ISSUE_WORK_CHECKPOINT.md`. GH-2/GH-7/GH-13/GH-19/GH-20 remain checked;
#365/#350/#372/#347/#358/#360 are verified CLOSED/COMPLETED and receive the
published commit links. Public #354 now distinguishes pushed work from releases.
There are 25 open issues, including the tracker; unresolved gameplay, imported
save, configuration and hardware reports remain open.

Nine committed-source/pinned-SDK suites pass 81 checks; one Git-metadata check
is skipped because the validation archive has no `.git` directory. Missing
local dependency fixture failures were resolved by supplying the pinned
toolchain and committed SDK source. Native runtime qualifications remain the
prior scoped runs; no new Android/Rally qualification is claimed.

A verified local archive preserves 137 worktree files and binary diffs from
all three repositories, with matching SHA-256 hashes after the push:
`.local/checkpoints/20261006T214213Z/worktree.zip`. Unfinished Rally/Android/SDK
changes remain uncommitted and are excluded from the push. Live saves, pinned
seeds and original game files are untouched. Publication receipt:
`.local/issue-triage/checkpoint-publication-20261006.json`.
