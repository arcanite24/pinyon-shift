# Feature backlog: the definitive way to play FH1

Created 2026-10-07 at `dev` `1c09921` (ShiftGlue `6d82bb4`) from a research
pass of 2026-10-07: an inventory of shipped features and open items in this
repository and its GitHub issues, a web survey of what players miss in FH1
and what made other fan ports and online revivals last, and a read-only
feasibility study of the candidates in the translated guest code. The
reports are not in the repository; their findings are summarised here.
Guest addresses come from static reading of
`.local/generated/default/pinyon_shift_recomp.*.cpp` (base build) and strings
from `.local/game/v4-images/default.v4.bin`. None of them has been confirmed
at run time unless a row says so.

This is the **central list of player-facing features**. Performance,
renderer, Android, low-spec, DLC and title-update work keep their own
backlogs; where a feature here belongs to one of them, the row points there
instead of repeating it:
[NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md) (NP),
[DLC_BACKLOG.md](DLC_BACKLOG.md) (DLC),
[TITLE_UPDATE_V4_BACKLOG.md](TITLE_UPDATE_V4_BACKLOG.md) (TU),
[PERFORMANCE_BACKLOG.md](PERFORMANCE_BACKLOG.md) (PB),
[DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md) (DR),
[LOW_SPEC_BACKLOG.md](LOW_SPEC_BACKLOG.md) (LS),
[ANDROID_PORT_BACKLOG.md](ANDROID_PORT_BACKLOG.md) (AP) and
[ROADMAP_FEEDBACK.md](ROADMAP_FEEDBACK.md) (community demand).

## Where the project stands

Pinyon Shift already covers what made Unleashed Recompiled and Zelda64Recomp
well received: native code, 60 and 120 fps at the right game speed, 1x-4x
internal resolution, ultrawide with a field of view setting, live settings
(F6), achievements, a trainer (F10), photo export, save backups, a mod API,
18 languages, every car pack, and Rally and the 1000 Club on the opt-in v4
build. The gaps are in four areas:

- **Audio:** MASTER VOLUME and MUTE only (`src/ui/settings_menu.cpp:502-512`).
  No radio controls, no per-channel volume, no custom music.
- **Input:** SDL opens only devices it maps as gamepads
  (`SDL_OpenGamepad`, SDK `src/input/sdl/sdl_input_driver.cpp:445`), so most
  PC wheels are ignored. Every non-XInput driver reports subtype 1 (gamepad).
  No gyro, trigger rumble or DualSense effects. Keys are rebound one per
  control in F6 > CONTROLS (FB-3.4); several keys per control only in the
  config file.
- **Online:** every LIVE export is a stub; matchmaking, Rivals, leaderboards,
  the Storefront and car meets have been gone since the servers closed on
  2023-08-22 ([forza.net](https://forza.net/news/forza-horizon-online-services-closure)).
- **Beyond-console graphics:** no draw-distance or LOD setting, no separate
  shadow or reflection quality, no HDR output (NP-4.8).

The open GitHub list is almost all bugs: of 27 open issues on 2026-10-07,
13 are `pscrash` reports with no triage yet, and the only open feature
requests are wheels (#337) and macOS (#310).

## Ranking

Demand is from [ROADMAP_FEEDBACK.md](ROADMAP_FEEDBACK.md) and the web survey;
effort is S under a week, M 1-3 weeks, L 1-2 months, XL longer.

| Order | Feature | Demand | Effort | Why this place |
| --- | --- | --- | --- | --- |
| 0 | FB-0 Playable first session | Largest barrier | S-M each | A new feature does not land if first runs crash |
| 1 | FB-1 Custom radio | #8, publicly promised | M | Data-path work on the existing mod system; testable without hardware; no emulator offers it |
| 2 | FB-2 Wheels and force feedback | #5, issue #337 | M (L for full FFB) | The game has its own wheel paths and FFB tuning; Xenia is XInput only, so this is unique to a native port |
| 3 | FB-3 Controller extras | Low-medium | S-M | Shares FB-2's driver work |
| 4 | FB-4 Draw distance and world detail | Not requested, seen by everyone | S spike, M | Data knobs show no gain (FB-4.1); needs the LOD code |
| 5 | FB-6 Offline Rivals and leaderboards | Medium; lost in 2023 | M-L | Asynchronous; the 1000 Club offline hook is the precedent |
| 6 | FB-9 Mod manager and existing mods | #7 | M | Zelda64Recomp's mod launch was its biggest moment |
| 7 | FB-5 Image quality beyond the console | Low-medium | M-L each | Shadows, reflections, HDR, temporal upscaling |
| 8 | FB-7 Livery and tune sharing | Medium; lost in 2023 | M (files), L-XL (Storefront) | File exchange first |
| 9 | FB-10 Quality of life | Mixed | S-M each | Many small wins |
| 10 | FB-8 Multiplayer | Strongest emotional demand | XL | LIVE only, no System Link found; research first |

Platforms (Linux, Steam Deck, macOS, Switch, Android) are the top request
but are platform work, tracked in FB-11 by pointer.

## Verification rules

- **Seeds only.** Never the AppData save (AGENTS.md, CLAUDE.md). Feature
  tests run through `tools/run-fh1-render-test.py` on a pinned seed from
  `tools/create-render-seed.py`.
- **Off by default until qualified.** A new feature that changes gameplay,
  audio or saves ships behind a setting, defaults off until its gate passes,
  and must not change a save that is played with it off.
- **Saves stay compatible.** A feature that writes profile data says so in its
  row, takes a save backup first, and is tested with save, reload and the
  feature disabled again.
- **Mods and cheats isolate.** Content that changes game data goes through the
  mod system, so the `user-modded` profile split applies.
- **No content in the repository.** Tools only: no music, liveries, car data
  or server traffic from Microsoft, Turn 10 or Playground.
- **No impersonation.** A local replacement for an online service is a host
  feature with its own name; it never claims to be Xbox LIVE or Forza
  services, and never contacts their domains.
- **Hardware features need hardware.** Wheel, DualSense and gyro rows are not
  done until checked on a physical device; until then they are "done in code".
- **Two inconclusive trials on one approach mean re-rank** (DR).

## Items

### FB-0 Playable first session (gate for everything below)

The community review found setup failures and crashes are the larger
barrier. These rows own the triage; the fixes land in NP and the GitHub
triage backlog.

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-0.1 | **Group the 13 untriaged `pscrash` issues** (#343, #345, #357, #361, #364, #370, #374, #377, #378, #383, #384, #385, #387) by crash signature and release; map each group to a known fix, a duplicate or a new root cause. | S | Not started |
| FB-0.2 | **First-session route on the current release:** intro, first race, first showcase, save and relaunch, ten minutes of free roam, from a fresh profile, on Vulkan at 1x and 2x. It becomes the gate each feature below must still pass. | S | Not started |
| FB-0.3 | **Open rendering bugs players see first:** cutscene and wristband corruption (#356, NP-2.9), boot over-exposure (#380), post-race hitching (#381), DOF (GH-21). Fix or label each. | M | In progress: #381 done 2026-10-16. The title's main loop steps on a vblank event raised every second guest vblank, and its render thread draws the newest finished step, so when a frame takes longer than two vblanks steps are skipped, and when the two drift apart a frame gets none (0 or 2 steps per frame at a flat frame rate). `pinyon_shift_step_backpressure` (on by default) holds the vblank raise while the main loop is two steps ahead of the render thread's swaps and raises the event at the next swap: race route at 2x and 120 fps, in-run A/B, frames with exactly one step 87 to 99 % (base) and 86 to 99 % (v4), game time more than 4 ms off the frame's wall time 12-14 % to 2-3 %; free roam 83 to 99.6 %; 60 fps unchanged; stock route gates pass on both builds. Earlier measurements (2026-10-10) used per-present tick counts, which count the loop's tick before its wait; the earlier equal-step patch and a hold of the main loop until the swap are rejected (site lessons). Details in site/findings/threads.toml (step and frame pairing) |
| FB-0.4 | **Reconcile stale rows** before planning from them: `DLC_BACKLOG.md:27,144,147` (done in TU), LS-4.1 status, NP-12/NP-14 shown as unstarted, NP-8.5's free camera (shipped). | S | Not started |

### FB-1 Custom radio (M)

**What the game has.** The radio is FMOD Ex, not XACT. Music is one bank,
`media/audio/radio/Radio_Music.fsb` (FSB4, 680 MB, 127 samples). The header
of every sample reads mode `0x90000200`; `0x200` is FMOD's MPEG flag, and
the data is plain MPEG-1 Layer III at 48 kHz and 160 kbps CBR, 480-byte
frames (mono for the 3D stations, stereo for Radio1-3), decoded in guest
software, not XMA (FB-1.3). `Radio_Music.lst` lists the source WAVs. `RadioSystem.xml` defines Radio1-3, `Radio4_Silent`
and 3D stations 5-9 (pre-race, Autoshow, workshop, paint shop, street race),
with 127 `MusicTrack` entries (name, artist, FMOD name, time-of-day
likelihoods). `RadioSoundbankInfo_Music.xml` holds each track's sample index,
event and ident offsets, sync points and length; its header says the game
generates it with the command-line option `generateradiosoundbankinfo` (the
string is in the v4 image). DJ lines are in `Radio_VO_<lang>.fsb`. All of
these are loose files, so whole-file overrides under a mod's `game/` folder
(`docs/MODDING.md:73-84`) can replace them without archive patching.

**What the console offered.** FH1 used the Xbox 360 custom soundtrack in its
minimal form: it sends only XMPSetPlaybackController (`0x0007001A`, through
`XMsgStartIORequestEx` in `sub_82A63F40`, called from `sub_82A63E90` and
`sub_82A63DB8`) and XMPGetPlaybackController (`0x0007001B`, through
`XMsgInProcessCall` in `sub_82A63FE8`, called from `sub_8247B0C0` and
`sub_82A63DB8`). It never drives the player; the dashboard played the user's
music and the game muted its own. `sub_823F2960` reads
`XAudioGetVoiceCategoryVolume(1)` and caches it at object+536. The SDK
implements both messages (`src/kernel/xam/apps/xmp_app.cpp:376-416`; setting
the controller broadcasts `0x0A000003`, `xmp_app.h:95`), only warns on
playlist playback (`:138`), and always returns volume 1.0
(`src/kernel/xboxkrnl/xboxkrnl_audio.cpp:43`).

Gate: a custom station plays in free roam, a race and the Autoshow; station
switching, the radio popup and DJ-free transitions work; the default radio is
bit-identical with the feature off; ten minutes without an audio dropout;
save, reload and disable leave the profile unchanged.

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-1.1 | **Find the guest's mute path.** Trace where the guest handles `0x0A000003` and what it does with the cached category volume; confirm at run time with a probe that takes the playback controller and reports volume 0. | S | Done (2026-10-10): FH1 polls `XMPGetPlaybackController` every frame and keeps its music silent while the controller is 1 (the system's player); its title music goes from RMS 0.007 to 0 within a second and comes back when the controller returns. The `0x0A000003` notification's data and voice category 1's volume (`XAudioGetVoiceCategoryVolume`, read in a loop) change nothing audible. Effects and ambience stay. |
| FB-1.2 | **Host music player ("your own music", the 360's behaviour).** A host player for a local folder or playlist (MP3, FLAC, Ogg through a decoder already licensed for the project), with next, previous, shuffle and volume in F6 and on a bindable key. Taking it over tells the guest a system player is active, so the game mutes its radio by its own path. | S-M | Done (2026-10-10, #420): MP3 (the SDK's FFmpeg MP3 decoder, on Windows x64, Linux x64 and Android) and 16-bit or float WAV everywhere, from `<state>/music` or `pinyon_shift_music_folder`, on its own SDL stream under the master volume. F6 > AUDIO: YOUR MUSIC, MUSIC VOLUME, SHUFFLE, NEXT and PREVIOUS TRACK; F9 and Shift+F9. FLAC and Ogg need decoders the SDK's FFmpeg doesn't build. |
| FB-1.3 | **Decode the formats exactly.** Parse `Radio_Music.fsb` (FSB4 headers, the unknown mode bit, MPEG frame layout) and `RadioSoundbankInfo_Music.xml` (what sync points and offsets mean); write a round-trip test that rebuilds the shipped bank byte-identically from its own samples. | S-M | Done (2026-10-10): FSB4 version `0x40000`, header mode `0x40`; 80-byte sample headers plus a `SYNC` block of three points (a 32-bit sample offset and a 256-byte name each: `SongStart`, `EventStart`, `IdentStart`; `R3_Teenager` spells the first `SongSTart`). The header block and every sample's data are zero padded to 32 bytes. All 127 music samples are whole 480-byte frames (1152 samples each) with the same unexplained mode bits `0x90000000`, so they are copied as they are. The info file is the sync points in milliseconds, rounded down, with the sample's index and length (`FileLength`); `SyncpointIndexIdentStart` is 2 and `OffsetStartNextTrack`/`SyncpointStartNextTrack` are always 0/-1. `build-fh1-radio.py --check-bank` rebuilds the music bank and all four VO banks byte for byte, so the tool computes the info file and the game's `generateradiosoundbankinfo` path is not needed. |
| FB-1.4 | **Station builder tool.** `tools/build-fh1-radio.py`: a folder of audio files becomes an FSB4 MPEG bank at 48 kHz stereo, merged `RadioSystem.xml` entries and a regenerated soundbank info file, written as a mod. Either compute the info file in the tool or run the game's `generateradiosoundbankinfo` path from a host flag; choose by FB-1.3. Replace a station or add tracks to one. | M | Done (2026-10-10, #420): any file FFmpeg reads is encoded to the bank's format and appended to a copy of the player's bank (stock indexes unchanged); the tool computes the info file, adds to or replaces the playlists of Radio1-3 (`--station` repeatable; `--replace` lowers `noRepeat` so the picker keeps a choice) and writes a `shares_save` mod under `<state>/mods/custom_radio`. On the 2026-09-27 seed with two test tones replacing all three stations, the title opened the mod's bank and XML files and played both tones in free roam after D-pad station changes. The track-name popup and a full track-to-ident transition are not checked yet. |
| FB-1.5 | **DJ and station identity.** Keep, mute or retime DJ lines (`Radio_VO_<lang>.fsb`) around custom tracks; optional custom station name through string-table overrides. | S-M | Not started |
| FB-1.6 | **Settings and launcher.** Radio volume apart from effects (check whether FMOD's channel groups or the category volume can carry it), a RADIO page in F6, and a launcher entry to build a station from a folder. | S | Not started |
| FB-1.7 | **Streaming limits.** Measure a bank of 2x and 4x the shipped size for streaming, seek time and memory; set the tool's limit from that. | S | Not started |

Risks: the info file ties sample order to offsets; a larger bank may exceed
streaming budgets; per-track time-of-day likelihoods need sensible defaults.

### FB-2 Racing wheels and force feedback (M; L for full FFB)

**What the game has.** The input module sits around `0x82BF8000-0x82BFFxxx`.
`sub_82BF80D0` (near `0x82BF8118`) and `sub_82BFBE20` (near `0x82BFC0E4`)
call the XInputGetCapabilities wrapper `sub_830EB918`, check for subtype 2
(wheel) and the force-feedback flag (bit 0), call `sub_8310C968`, require a
result of 5 or more, and set a flag at +4. The XInputSetState wrapper
`sub_830EB930` and its asynchronous form `sub_8310CBC8` also branch for a
wheel with FFB (and swap the motors on kernels before 2.0.5611; the SDK
reports 2.0.65535, so no swap). `sub_8310CBC8` resolves ordinal 442,
`XamInputGetUserVibrationLevel`, through `sub_8310C788`; the SDK stubs it
(`xam_input.cpp:213-231`). `sub_82BFC6F0` picks that path (`sub_82BFA428`, flag
at +4244) or `sub_830EB930`. `sub_82BFBA90` uses `XamInputRawState` and
`XNotifyGetNext` with a 16-byte ID comparison at `0x822DAD70`, possibly the
Speed Wheel. The force model is tuned in `media/ControllerFFB.ini` (inertia,
friction, damper, spring, dynamic scale, spring against speed, rear slip),
loaded as `Game:\Media\ControllerFFB.ini`, with `CSteeringWheelFilter` and
`CCarPresentationSetSteeringWheelAngle` in the image. Its output is two
16-bit motor values.

**What exists.** Only the XInput backend passes a device's real subtype
(`xinput_input_driver.cpp:175-176`); SDL, keyboard and null drivers report 1.
No DirectInput, SDL joystick or SDL haptic code exists.

Gate: on at least two wheel brands, the guest sees a wheel, uses its wheel
steering, and FFB follows the car (centring at speed, lightening on rear
slip); pedals and clutch work in manual with clutch; the gamepad path is
unchanged.

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-2.1 | **Guest wheel contract.** Report subtype 2 with the FFB flag from a test driver and trace `sub_8310C968`, the +4 and +4244 flags, which steering and filter path engages, and what the two motor values mean under a wheel (constant force? spring?). Check whether the ordinal-442 stub zeroes output. The subtype half exists as a switch: `input_report_wheel_subtype=true` makes the SDL driver report `XINPUT_DEVSUBTYPE_WHEEL` for a detected wheel (off until the trace says what the title does with it). | S-M | Switch ready, trace not started |
| FB-2.2 | **Wheel driver.** SDL3 joystick (not gamepad) devices with a wheel or user-chosen profile: steering, separate throttle, brake and clutch axes, H-pattern and sequential shifter buttons, mapped onto the guest's wheel state with subtype 2. DirectInput only if SDL misses devices FB-2.4 needs. | M | Not started |
| FB-2.3 | **Force feedback.** Translate the guest's motor values into an SDL haptic constant-force effect on `SDL_HAPTIC_STEERING_AXIS`, with host spring and damper scaled by the values in `ControllerFFB.ini`. Then decide whether to recreate the ini's model host-side from the car's self-aligning torque (L). | M-L | Not started |
| FB-2.4 | **Settings.** A WHEEL page in F6: rotation, steering linearity and deadzone, pedal curves and inversion, combined or separate pedals, FFB gain and centring, a calibration step, and per-device profiles. | S-M | Not started |
| FB-2.5 | **Device matrix.** Logitech (G29/G920/G923), Thrustmaster (T300/T150/TMX), Fanatec, Moza; Windows and Linux (kernel quirks such as Moza's FIX_WHEEL_DIRECTION). Record each in a tested-hardware table. Closes GH-9 and #337. | M | Needs a person |

### FB-3 Controller extras (S-M)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-3.1 | **Stick deadzones and response curves** on the host (none today: `sdl_input_driver.cpp:495-590` passes axes raw), per stick and trigger, with a test view in F6. | S | Not started |
| FB-3.2 | **Gyro steering** for DualSense, DualShock 4 and Switch Pro: `SDL_SetGamepadSensorEnabled`, blend into left-stick X with recentre and sensitivity. | S-M | Done as DS-6.0 (tilt steering, off by default) in the [DualSense backlog](DUALSENSE_BACKLOG.md); play-tested on a DualSense |
| FB-3.3 | **Trigger rumble and adaptive triggers.** `SDL_RumbleGamepadTriggers` for Xbox controllers; DualSense resistance through `SDL_SendGamepadEffect`, derived from throttle and brake input plus the guest's motor values (the guest exposes nothing trigger-specific, so this is an approximation). | M | DualSense adaptive triggers done (DS-1 to DS-3, verified over USB on Windows, off by default; [DualSense backlog](DUALSENSE_BACKLOG.md#results)); Xbox trigger rumble not started |
| FB-3.4 | **In-menu keyboard binding editor** and analog ramp for keyboard steering and throttle (NP-6.1). | S-M | Editor done (#401): choosing a key row in F6 > CONTROLS asks for a key or mouse button, which replaces the row's keys and applies at once; RESET KEYS restores the defaults. The analog ramp is not started |
| FB-3.5 | **Button glyphs per device** in host UI; guest HUD glyphs stay Xbox (NP-6.2). | S | In part as DS-5.0: our own cross and circle in the host UI's help bar, PlayStation names in the mapping assistant ([DualSense backlog](DUALSENSE_BACKLOG.md)) |
| FB-3.6 | **Steam Input and Deck layout** (NP-6.3, NP-12.8). | S | Needs a person |

### FB-4 Draw distance and world detail (S spike, M)

The image names LOD and distance keys that look data-driven: `CarLODTransDist`,
`CarLODTransDistTraffic`, `CarFocusLODMinMax`, `CarForceNoLOD0`,
`LOD1_Threshold`/`LOD2_Threshold`, `LOD0_Count_Scale`..`LOD3_Count_Scale`,
`CrowdLODCountScales`, `GrassLODDist`, `GrassLODFadeRange`,
`LODdist_Near`/`Far`, `AI/Traffic/VehiclePosition/MaxHighLodDistance` and
`MaxMediumLodDistance`, `CamFarClip`, and
`Game:\Media\Cars\shared\ShaderSettings\SLod.xml`. `renderscenarios.zip` holds
per-player-count budgets (`1-Car_Race.xml`, `12-Car_Race.xml`,
`16-Car_*`), compressed with FH1's method 21.

**The render scenarios, read 2026-10-07** (35 members, extracted with
`pinyon_shift_fh1_archive_extract`). Each is a `<DynamicRenderSettings>`
list layered over `Global.xml`. The race scenarios
(`Horizon_Race.xml`, `N-Car_Race.xml`) set `FrameRate` 30,
`CarLODThresholds lod1="2" lod2="4" count="6"`,
`CarLODTransDist near="15.0" far="25.0" veryfar="50.0"` (cars change LOD at
15, 25 and 50 m), `CarLODTransDistTraffic` (LOD2 22 m to LOD5 100 m),
`CarFocusLODMinMax`, `CarMinWheelLOD 1`, crowd draw and LOD count scales,
`ParticleRateScale` and `EnvMapFrequencyScale` 1.0. `Multiplayer.xml` forces
`CarForceNoLOD0`; `1-Car_Race.xml` keeps the player's car at LOD 0.
`PhotoMode.xml` adds only `CarMinWheelLOD 0`, `CollidableShadows 1`,
`SoftParticles 1` and `DepthOfField 0`. Which scenario free roam uses is
not traced, and terrain, tree and grass distances are not in these files.

Gate: less visible pop-in in a side-by-side capture of the same route; no new
streaming stalls, no crash in a 30-minute drive, and guest memory headroom
measured (512 MB guest, `CLoadAndWaitForLOD0Cars`).

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-4.1 | **Find the keys.** Decompress `renderscenarios.zip` with `tools/patch-fh1-archive.py`'s reader, locate each key above in data or code, and record which are loaded from files and which are constants. Trace which scenario free roam selects. | S | Done 2026-10-11, no data knob found. Every key traced is recorded on [World and tracks](https://arcanite24.github.io/pinyon-shift/game-world/). Track grass, crowd and scene distances (`TrackSettings.xml`) and the car LOD keys (`CarLODTransDist`, its traffic table, `CarLODThresholds`) change nothing visible, even at extreme values; scenery is culled by precomputed PVS zones; `SLod.xml` is a car shader file and `CamFarClip` a code default. FB-4.2 now needs the code that picks a model LOD for scenery and cars, found by tracing which LOD a draw uses |
| FB-4.5 | **Photo mode detail in gameplay.** A setting that applies `PhotoMode.xml`'s detail keys (`CarMinWheelLOD 0`, `CollidableShadows 1`, `SoftParticles 1`, not its DOF change) to every scenario through XML merges. Trace what the code does on `IRenderThreadInPhotoModeInternal` and `IPresentationInPhotoMode`, and the `highrescubemap` option, for quality switches that are not in data. Photo capture's accumulation supersampling (`MultiSampleAndAccumulate`, `AccumulateWeightedFrame`) and BIG SHOT need a still scene and are not real-time features; the resolution scale is their real-time counterpart. Gate: a visible difference in an A/B capture, then cost measured on the race. | S-M | Tried 2026-10-11 for #421: merging the three keys into every gameplay scenario showed no visible difference in race A/B captures at 1x, so the gate fails and nothing ships. The code-path traces remain |
| FB-4.2 | **World detail preset.** A WORLD DETAIL setting (ORIGINAL, HIGH, ULTRA) that raises car, crowd, grass and traffic LOD distances and far clip through XML merges or a host hook; measure CPU, GPU and guest memory per step. | M | Not started |
| FB-4.3 | **Traffic and crowd density** as separate options, shared with LS's "optional reductions to game systems" so the same setting lowers them on weak machines. | M | Not started |
| FB-4.4 | **Memory ceiling.** Measure guest heap headroom in the worst scenario (16-car race, Autoshow) and stop the preset before it. | S | Not started |

### FB-5 Image quality beyond the console (M-L each)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-5.1 | **Shadow resolution apart from internal scale.** Override the shadow-map targets and viewports for those passes only in the native executor (cascades are set in shaders, `CSMShadowMapLevel0TM`). Fix NP-4.10's 2x-4x shadow artifacts first. | L | Not started |
| FB-5.2 | **Reflections.** Raise the dynamic cubemap's size or update rate (`DynamicCubemap`, `EnvMapFrequencyScale`), from data if FB-4.1 finds it, otherwise in the executor. | M-L | Not started |
| FB-5.3 | **HDR output.** The presenter only selects sRGB swapchains (`src/ui/vulkan/vulkan_presenter.cpp:1258-1293`) and the guest tonemaps to SDR; take the scene before the tonemap and add HDR10 or scRGB presentation (NP-4.8: plumbing M, quality L). **Stage 1 done (2026-10-10, #417):** `present_hdr` presents to an scRGB swapchain where the surface offers it; the guest output and host UI paint into an SDR stand-in per swapchain image as before, and a last pass decodes its sRGB and scales white to `present_hdr_paper_white_nits` (DISPLAY > HDR, HDR PAPER WHITE, shown when the display has HDR on). Checked on Multivac's LG TV (Windows HDR on, 4K 120 Hz) by a temporary readback: within 0.5 % of the expected scRGB values; off, nothing changes. **Stage 2 done (2026-10-10):** FH1 resolves its float scene to an 8888 texture before the last composite, so no range above SDR white reaches the front buffer; instead the scene's highlights are expanded from linear luminance 0.5 up to `present_hdr_peak_nits` at SDR white (DISPLAY > HDR HIGHLIGHTS, OFF or 400 to 1500 nits, default 1000), and the HUD and menus stay at the paper white. The native executor copies the front buffer at the first draw through its `2_10_10_10_AS_10_10_10_10` view (the HUD) after the `2_10_10_10` composite; the swap compares that copy with the swapped frame (order-independent, so R/B swaps do not matter) and writes the HUD coverage into the guest output's alpha; the presenter carries it into the stand-in's alpha, where host UI adds its own, and the last pass expands only where the alpha is low. Frames without the composite (menus, loading) stay opaque, so all paper white. Readback on the race route: menus never expanded, HUD pixels at most 1.1 % above paper white (rounding), race highlights up to about 980 nits; `fh1-race-retire` passes with HDR on and off at the same present rate (115 Hz); validation clean. Judging the curve on the TV is left to the maintainer. **Stage 3 done (2026-10-10, #442):** the maintainer's TV check found washed-out colors, flames and headlights too bright and white, brake lights not expanded, and flicker on the translucent prestige meter. The last pass now decodes the stand-in with gamma 2.2 like an SDR display (`present_hdr_gamma`, 2.4 or piecewise sRGB on DISPLAY > HDR GAMMA). `present_hdr_peak_nits` is now the display's peak, and SDR white in the scene goes `present_hdr_highlights` of the way to it (HDR HIGHLIGHTS OFF, LOW, MEDIUM (0.5, default) or HIGH). The expansion follows a mix of 0.75 of the largest channel and 0.25 of the luminance, scaling all three channels, so a red brake light expands with its hue. The HUD mask is binary (any sorted-channel change above 0.006, grown by a pixel) instead of a soft 2-bit alpha. `present_hdr` switches at run time: the paint returns connection-outdated and the reconnection recreates the swapchain in the other format. DISPLAY > HDR COMPARE shows piecewise-sRGB SDR on the left half beside the HDR right half (not saved). DISPLAY > HDR CALIBRATION steps through test patterns that the last pass draws under the menu (`present_hdr_test_pattern`) in a band the menu leaves undimmed: black (1-6 % squares, for the TV's brightness), paper white (a white square beside gray steps on mid gray, setting `present_hdr_paper_white_nits`) and peak (a square at the tested peak in a 10000-nit field that disappears at the display's peak, setting `present_hdr_peak_nits`). Checked on Multivac by a temporary readback: gameplay highlights at 600 nits (paper white 200, peak 1000, MEDIUM) within 1.4 % of the formula; no gameplay pixel counted as HUD on the sampled rows; patterns, compare halves and divider exact; off, on, off and on again recreates the swapchain each time, validation clean. The look on the TV is again the maintainer's to judge | L | Done; TV check pending |
| FB-5.4 | **Upscaling and AA.** FSR 1 quality presets and sharpness (README "next"), temporal upscaling (DR-5.4, researched), non-integer scale (NP-4.8). Tracked there. | - | Pointer |
| FB-5.5 | **Modern bloom, motion blur and DOF** (LS "Requested defaults"). Tracked there. | - | Pointer |
| FB-5.6 | **Texture packs on Vulkan.** Done 2026-10-12 ([#518](https://github.com/arcanite24/pinyon-shift/issues/518)): the dump, lookup and DDS code moved into a shared ShiftGlue module, and the Vulkan cache uploads replacements, the same size or 2x/4x/8x in a larger image of its own (the old image retired until its submission completes). Free roam on an RTX 4080 with every DXT1 texture replaced by a solid colour: 478 replaced at 1x and 449 at 2x of 485 in the pack, reload mid-run works, and frame times match a run without a pack (median 8.3 ms). DXT replacements need a GPU with BC formats (#516). The legacy D3D12 backend reached neither dumps nor replacements on that route and was not investigated. | S-M | Done |

### FB-6 Offline Rivals and leaderboards (M-L)

The online leaderboards and Rivals ghosts went with the servers. The 1000
Club offline work (TU-7) shows the pattern: answer the server check only for
the callers that need it (`sub_824127B8`, service at `[0x833CABB0]`) and
replace the web call with a local queue (`sub_829490D8` replaced, commit via
`sub_824D8300`).

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-6.1 | **Trace Rivals and leaderboard calls**: which web services and LSP endpoints they use, what a ghost and a leaderboard row contain, and where the game stores `GameplayLog` (NP parking lot). | S-M | Not started |
| FB-6.2 | **Local leaderboards.** Personal bests per event, speed trap and speed zone, kept in a host file beside the profile and shown through the game's own leaderboard screens. | M | Not started |
| FB-6.3 | **Local Rivals.** Race your own recorded ghosts, then ghosts exchanged as files (import or export in the launcher). | M-L | Not started |
| FB-6.4 | **Optional community server**, only after FB-6.2 and FB-6.3: a self-hostable service for shared leaderboards and ghosts, under the project's own name. | L | Not started |

### FB-7 Livery, vinyl and tune sharing (M; L-XL for the Storefront)

The livery editor is local (`CLiveryEditor`, `Livery.zip` with 1,372 members,
`LiveryFileName` in the save database). The Storefront (`Forza::CStorefront`,
`CStorefrontUploadManager`) needs Forza web services over `XamXStudioRequest`
(`xam_misc.cpp:786`), LSP endpoints (`/lsp/enumerate.ashx`), the `XamXlfs*`
upload queues (stubs, `xam_misc.cpp:813-818`), signed-file checks
(`CSignedFileSecurity`) and the same server gate as the 1000 Club.

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-7.1 | **Qualify the livery editor**: paint, vinyl groups, save, reload, apply to a car, photo. | S | Not started |
| FB-7.2 | **Export and import files.** A host tool and launcher entry that copies liveries, vinyl groups and tunes between profiles as files, with a backup first. | M | Not started |
| FB-7.3 | **Local Storefront.** Pass the gates, emulate the web, LSP and upload calls against a shared folder. Only after FB-7.2 and FB-6.1 show the formats. | L-XL | Not started |

### FB-8 Multiplayer (XL; research first)

FH1 appears to be LIVE only. "System Link" strings are absent from the v4
image (localized string tables were not searched), and FH1 is not on Xenia
Canary's netplay compatibility list. The guest imports about 30 socket calls
(including asynchronous `WSA*`), XNet addressing, key exchange and QoS, and
uses session messages to app `0xFB` (create `0x10`, delete `0x11`, start
`0x14`, end `0x15`, search `0x1C`, and others) through `sub_830A3510`..
`sub_830A3D30`. Strings show `Network::PartyLobby`,
`CLobbyHostMigrationHandler`, `Xls::HopperClient`, `CPeerNet`,
`DirectPlayPeer` and `CRaceSynchronizationManager`. The SDK returns a
loopback XNet address, fails address translation and QoS, reports no
Ethernet link, and stubs `WSASend`, `WSARecv` and `WSAEventSelect`
(`xam_net.cpp:438-508,560,1003-1051`). After the shutdown, Wikipedia reports
friends exploring together through LIVE's peer-to-peer service, which
suggests sessions were peer-hosted and only matchmaking was on servers; this
is unverified.

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-8.1 | **Two-instance probe.** Unique XNet addresses and an address table, a cable link, working asynchronous WSA calls; see how far two local instances get toward a session. | S-M | Not started |
| FB-8.2 | **Map the session flow**: hopper and LSP calls to bypass, session messages to emulate, packet framing (VDP), host migration. Decide go or no-go with an estimate. | M | Not started |
| FB-8.3 | **LAN free roam**, if FB-8.2 is a go: a host session service over LAN broadcast, then a small self-hostable rendezvous server. Physics sync across differently timed hosts (decoupled frame rate) is the main risk. | XL | Not started |

### FB-9 Mods ecosystem (M)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-9.1 | **Mod manager in the launcher**: install from a ZIP, enable, disable and order, show conflicts (README mid term). | M | Not started |
| FB-9.2 | **Existing FH1 mods.** Check the XE Mod (FH2 and Fast & Furious cars in FH1, ModDB) through the override workflow and write compatibility guidance. | S-M | Not started |
| FB-9.3 | **Mod templates** for the features above: a radio station (FB-1.4), a world detail preset (FB-4.2), a livery pack (FB-7.2). | S | Not started |
| FB-9.4 | **Menu insertion and Lua** (NP-11.3, NP-10.4). Tracked there. | - | Pointer |
| FB-9.5 | **Car import** from FH2, and research on Assetto Corsa content (README longer term). | XL | Not started |

### FB-10 Quality of life (S-M each)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-10.1 | **Trainer v2**: freeze (blocked on the physics body, NP-8.1) and native-map teleport (#485), unlock cars and events, any car in any event, remove car limits (NP-8.5-8.7). | M | Pointer |
| FB-10.2 | **AI driving for the player's car** in the trainer, reused by automated routes (README mid term). | M-L | Not started |
| FB-10.3 | **Photo mode upgrades**: free camera with field of view, roll, depth of field and HUD hidden, writing through photo export. | M | Not started |
| FB-10.4 | **Shorter loading and transitions** (README mid term; PB owns measurement). | L | Pointer |
| FB-10.5 | **Accessibility**: HUD and subtitle scale, colour filters, hold-to-toggle inputs (NP parking lot). | M | Not started |
| FB-10.6 | **Discord rich presence** (NP parking lot): current event, car and area. | S | Not started |
| FB-10.7 | **Update from inside the launcher**, keeping saves and settings (README next). | M | Done 2026-10-10: both launchers check GitHub releases for their channel, download the platform's asset, verify GitHub's SHA-256 digest, swap the launcher files (the .app bundle on macOS) and restart; the source folder drops files a release removed. Tested on Windows end to end, Linux (WSL) and macOS (signed bundle swap) at the file level |

### FB-11 Platforms (pointers)

| ID | Item | Owner |
| --- | --- | --- |
| FB-11.1 | Linux build and launcher (never configured on Linux yet; one player runs the Windows build under GE-Proton, #388) | NP-12.1, 12.2, 12.7 |
| FB-11.2 | Steam Deck qualification: gamescope, 1280x800, Steam Input, suspend and resume | NP-12.8, LS-0.1 |
| FB-11.3 | macOS through MoltenVK | NP-13 |
| FB-11.4 | Android install and sustained performance | AP, A60 |
| FB-11.5 | Nintendo Switch feasibility | ROADMAP_FEEDBACK |

### FB-12 Second research round: play enhancements only a native build can offer

Research pass of 2026-10-11 at `dev` `713a1c8`, not about performance:
an inventory of shipped and proposed player features across every backlog,
a survey of the mod API and `gamedb.slt` (221 tables), a static read of
the base image's strings and archives, and a web survey of what made other
recompiled and decompiled ports popular (Unleashed Recompiled,
Zelda64Recomp, Ship of Harkinian, 2 Ship 2 Harkinian, SpaghettiKart, Banjo:
Recompiled) and what FH1 players complain about (GTPlanet, forza.net,
reviews; Reddit and ModDB comments were not reachable). Guest findings are
on [Systems and leftovers](https://arcanite24.github.io/pinyon-shift/game-systems/); only the launch options have been checked at run time (FB-12.0).

**The main lever.** The retail executable still has about 300 developer
launch options (`launch`, `trackname`, `numaicars`, `allowskipvoiceover`,
`chooseillegalcarforevent`, `splitscreenlaunch`, ...) as byte flags in one
object built at boot. FB-12.0 found that retail never fills them from the
command line or `cmdline.txt`, but a host or mod that writes a flag at boot
changes the game: `nohud` removed the whole HUD. So each option costs one
write and one check, through the mod API's `write_guest`, and the string and
number options behind FB-12.2 need their storage traced first.

**What players ask for** (most to least often in the sources found):
solid barriers and little off-road freedom; no tuning; repetitive events
and wristband grind; too few cars; event car restrictions; a quiet engine
mix. Other ports were best received for new ways to play (randomizers,
track editors, co-op), drag-and-drop mods, restored original content and
control options.

Ranked by player value for the cost, then by how much is already in place.
Effort as above; "route" names the cheapest path found.

| Rank | ID | Enhancement | Route | Effort | Confidence |
| --- | --- | --- | --- | --- | --- |
| - | FB-12.0 | **Launch-option probe.** Find how to set the options in retail and check them | Probe mod on the free-roam route | S | Done 2026-10-11: the `cl` cvar and `cmdline.txt` do nothing (retail never parses them); writing the flag bytes at boot works (`nohud` hides the HUD; `showframerate` shows nothing). Addresses and offsets on [Systems and leftovers](https://arcanite24.github.io/pinyon-shift/game-systems/#launch-options) |
| 1 | FB-12.1 | **Quality-of-life switches** ([#477](https://github.com/arcanite24/pinyon-shift/issues/477)) as F6 toggles: skip voice-over and tutorials, no splash or attract video, clean HUD, hide cockpit glass, zoomed-out minimap, no camera vibration, auto-reset off (`NoHandOfGodReset`) | Flag writes at boot (FB-12.0), or `GameTunableSettings.ini` merges | S each | Done: F6 > GAMEPLAY has the voice-over skip, the automatic reset and the idle intro replay; the HUD hides with F2. `skiptutorials` (Kinect showroom only), `nocameravibration` and `hidepoipins` (never read) do nothing; see [Systems and leftovers](https://arcanite24.github.io/pinyon-shift/game-systems/#launch-options) |
| 2 | FB-12.2 | **Free Race.** ([#478](https://github.com/arcanite24/pinyon-shift/issues/478)) A host menu that builds any race FH1 never offered: route, laps, opponents and their cars, AI skill, time of day, traffic. 145 active tracks, 85 used by events | `launch`, `trackname`, `ribbon`, `numlaps`, `numaicars`, `aicar%d`, `aiskill`, `timeofdayindex`, `numtrafficcars` | S-M | Probable |
| 3 | FB-12.3 | **Any car in any event** ([#479](https://github.com/arcanite24/pinyon-shift/issues/479)) (a new route to FB-10.1 and NP-8.7) | Hook in the `EventRestrictions` parser | S | Done 2026-10-12: TRAINER > WORLD > ANY CAR IN ANY EVENT (`cheat_any_car_events`, hot) lifts the make, year and other restrictions and the event's class (`fh1-trainer-any-car`); the developer options are read nowhere. Marking the event card is still open under NP-8.7. Details on [Cars, events and DLC](https://arcanite24.github.io/pinyon-shift/game-content/#event-restrictions) |
| 4 | FB-12.4 | **Split-screen spike.** ([#480](https://github.com/arcanite24/pinyon-shift/issues/480)) The code survives: `CSplitscreenLobby`, `CHudSplitscreen`, `948_HUD_Split_Screen`, `Splitscreen_Race.xml`, per-car split-screen camera offsets. Two-player local races would answer the strongest demand (multiplayer) without a network | `splitscreenlaunch`; the second pad through the input layer | S spike, L to ship | Code present; working unknown |
| 5 | FB-12.5 | **Telemetry out.** ([#481](https://github.com/arcanite24/pinyon-shift/issues/481)) UDP in a "Data Out"-style layout for SimHub, dashboards and motion rigs; then the game's own telemetry pages (`CTelemetryHud`, `968_TELEMETRY`), whose data sources lead to RPM, gear and slip | Native mod; v1 from the pose hook, v2 needs vehicle-sim offsets | M | Done (v1, 2026-10-16): F6 > GAMEPLAY > TELEMETRY OUT (UDP), FM7 Dash packets to `telemetry_udp_target` with RPM, redline, speed, gear and per-wheel slip from the DualSense car read; a race route sent 8,450 packets at RPM up to 7,904 and 34 m/s. Motion, position and inputs still 0. Inputs, idle RPM, wheel speeds, slip angles, suspension travel and the game's low rumble motor as surface rumble added after (2026-10-16); `telemetry_probe` records candidates for the motion, kerb and collision fields |
| 6 | FB-12.6 | **Fair AI.** ([#482](https://github.com/arcanite24/pinyon-shift/issues/482)) No rubber-banding, and a level above Unbeatable | Runtime hooks on the AI config at car spawn, the event difficulty and the skill adjustment (the database rows could not reach v4 or Android) | S | Done 2026-10-12: F6 > GAMEPLAY > AI OPPONENTS (`pinyon_shift_ai_opponents`, from the next event) picks STOCK (the game unchanged), NO RUBBER-BANDING (rubber band, catch-up, far-behind boosts and the post-race skill adjustment off) or HARD (the same, every difficulty one level up and the hardest at skill 1); it plays the player's own profile on Windows, Linux, macOS, Android and the v4 build. On `fh1-ai-gap` (base), stock AI spent 50-55 of about 70 samples rubber-banding with torque cut to 0.6; with NO RUBBER-BANDING or HARD none did, and HARD drove skills 33-39 instead of 49-55. The v4 build and the Odin 2 Portal (Android) gave the same counts The race-start and rival torque boosts are in code and stay. Records on the site's [Systems and leftovers](https://arcanite24.github.io/pinyon-shift/game-systems/#ai-opponents) page |
| 7 | FB-12.7 | **Day length.** ([#483](https://github.com/arcanite24/pinyon-shift/issues/483)) "A day lasts N minutes", real-time clock, golden-hour loop; today the trainer only holds an hour | `time_of_day.request` takes a rate; needs `call_guest_fp` (float arguments) in the mod ABI | S | Done (2026-10-16): TRAINER > WORLD > DAY LENGTH (`cheat_day_length_minutes`) drives the time-of-day float from the game delta, no `call_guest_fp` needed; 12-minute day measured at 120.00 game s per real s (`fh1-day-length`) |
| 8 | FB-12.8 | **Drive traffic and hidden cars.** ([#484](https://github.com/arcanite24/pinyon-shift/issues/484)) | Explicit qualified sales list; garage and paint checks | S-M | Revised for #669: `hidden_cars` now lists four player-model variants. All 18 traffic entries are excluded; the prior bus drive/T440 race did not qualify garage or paint. Existing purchases are preserved and a backed-up selection recovery is available. [Audit and recovery](HIDDEN_CARS.md). |
| 9 | FB-12.9 | **Teleport, fast travel anywhere and a custom GPS waypoint** ([#485](https://github.com/arcanite24/pinyon-shift/issues/485)) through the game's own fade-and-stream path, which avoids FB-10.1's physics-body blocker | `CTeleportCarToFastTravelDestination`, `fast_travel.xml`; `CSetSatNavDestinationPos` | M | Probable |
| 10 | FB-12.10 | **Atmosphere presets** ([#422](https://github.com/arcanite24/pinyon-shift/issues/422)): clear, misty morning, the game's own fog templates and colour grades | `dynamicpost.zip` fog, bloom, vignette and grading templates | S-M | Probable |
| 11 | FB-12.11 | **Audio mixer** ([#486](https://github.com/arcanite24/pinyon-shift/issues/486)): engine, tyres, wind, ambience and music sliders, and a dynamic-range option (the game has a TV compressor set). Answers the quiet-engine complaint; extends FB-1.6 | `AudioEngineConfig.xml` category levels, `AudioMixerSnapshots.xml` | S-M | Done: F6 > AUDIO scales the Gameplay snapshots' levels and can bypass the compressor; the `AudioEngineConfig.xml` levels do nothing in free roam ([Audio and radio](https://arcanite24.github.io/pinyon-shift/game-audio/#audio-engine)) |
| 12 | FB-12.12 | **Camera editor** ([#487](https://github.com/arcanite24/pinyon-shift/issues/487)): live chase height, distance, FOV and stiffness; wheel and car-relative replay driving views; immersive camera on v4 | Loaded `CameraSettings.ini` tuning and per-car offsets; explicit `merge-update/media.zip/camera/cameraphysics.xml` | S-M | Done: Windows disc/v4 pinned-seed driving routes qualify the controls, restoration and four immersive motion groups; [camera editor](MODDING.md#camera-editor) |
| 13 | FB-12.13 | **Photo mode unlocks** ([#488](https://github.com/arcanite24/pinyon-shift/issues/488)): camera through walls, wider aperture and zoom, larger free-camera bounds (a cheaper start on FB-10.3) | `disablephotomodecollisiondetection`, `allowhighzoomaperture`; `PhotoModeCam`, `FreeCam` sections | S | Done 2026-10-16: PHOTO CAMERA THROUGH WALLS (`disablephotomodecollisiondetection`, +4921) confirmed with `fh1-photo-camera-walls`; `allowhighzoomaperture` has no reader; the `photo_mode_limits` mod widens `PhotoModeCam` height, bounds and zoom (`fh1-photo-mode-limits`, base build) |
| 14 | FB-12.14 | **Head tracking** ([#489](https://github.com/arcanite24/pinyon-shift/issues/489)) from OpenTrack or TrackIR, fed into the game's Kinect head-tracking path (sensitivities and inputs survive) | `HeadTracking/*` settings, `HeadTrackingX..Pitch` inputs; host UDP receiver | M | Probable |
| 15 | FB-12.15 | **Rally map in free roam.** ([#490](https://github.com/arcanite24/pinyon-shift/issues/490)) The UDLC mod already does this on consoles and Xenia, so the data allows it | Mod using the Rally DLC the player imported; fast travel in and out | M | Probable (prior art) |
| 16 | FB-12.16 | **Festival pacing pack** ([#491](https://github.com/arcanite24/pinyon-shift/issues/491)): cheaper cars and upgrades, larger payouts, a shorter XP curve; answers the grind complaint | `Data_Car.BaseCost`, `List_Upgrade*`, `Events.CashPrize`, `PlayerLevelDef` SQL; check an existing save recomputes its level | S | Probable |
| 17 | FB-12.17 | **Saved replays and video export.** ([#492](https://github.com/arcanite24/pinyon-shift/issues/492)) Keep replays as host files, and render one offline at a fixed time step | Main/attached replay streams and separate initialization; [contract and gates](GAMEPLAY_REPLAYS.md) | L | Research: base-disc read-only probe; persistence, restart equivalence and export not implemented |
| 18 | FB-12.18 | **Triple screens.** ([#493](https://github.com/arcanite24/pinyon-shift/issues/493)) Three angle-correct views from one PC, from the game's linked-console mode | `CMultiscreenServer`/`Client`, `MultiscreenView`, `MultiscreenDegreesBetweenScreens` | M-L | Probable |
| 19 | FB-12.19 | **Second-screen map** ([#494](https://github.com/arcanite24/pinyon-shift/issues/494)): a LAN web page with the live map, position, collectibles and markers (FH1 had a SmartGlass map) | Pose hook, collectible offsets, a small host HTTP server | S-M | Confirmed inputs |
| 20 | FB-12.20 | **Breakable barriers spike.** ([#495](https://github.com/arcanite24/pinyon-shift/issues/495)) The most common FH1 complaint is solid fences and walls. Find whether scenery objects carry a solid or breakable flag in data or code; ship only as an option | `SmashableObjectTypes.xml` lists the smashable types (`Fence`, `Flyer`, `Mailbox`, `RaceActivation`); `CollObjs.xml` places 21,877 objects with physics types | S spike | Guess |

Added on request after the ranking, larger than the 20:

| Rank | ID | Enhancement | Route | Effort | Confidence |
| --- | --- | --- | --- | --- | --- |
| + | FB-12.21 | **Import cars from Assetto Corsa** ([#496](https://github.com/arcanite24/pinyon-shift/issues/496)): a tool that turns a permitted car the player supplies into an FH1 car mod; refuses encrypted and Kunos cars | `.carbin` writer (round-trip an FH1 car first), `.xds` encoding, physics and database mapping, closest FH1 engine bank | XL; the `.carbin` spike is the go or no-go | Guess |
| + | FB-12.22 | **World editor** ([#497](https://github.com/arcanite24/pinyon-shift/issues/497)): a `world/` mod format, an in-game placement editor on the free camera, custom routes and events, then re-used scenery and new geometry | `CollObjs.xml`, `GameObjs.xml`, `TrackRoute*.xml` and `gamedb` are plain data; `.bix`, PVS, `.col` and `.nav` need writers | S-M (format) to XL (new roads) | Probable for the data tiers |
| + | FB-12.23 | **Dual-screen devices** ([#499](https://github.com/arcanite24/pinyon-shift/issues/499)): map, touch controls, dashboard and quick actions on the AYN Thor's bottom screen, later on any second display | An Android `Presentation` with its own host-drawn Vulkan surface; shares the map with #494 | M | Probable; display discovery on the device decides |
| + | FB-12.24 | **FH2 world and cars** ([#501](https://github.com/arcanite24/pinyon-shift/issues/501)): FH2's Xbox 360 world and cars from the player's disc, first as a separate destination like the Rally map, then joined to Colorado by a road that hides the track switch | Rally's separate track (`ColoradoDirt`, `RibbonConfiguration`); XE's FH2 cars; format survey shared with Lavender Shift | Cars M-L; world L-XL; joined XL | Cars probable; world a guess until the format survey |

Also considered, kept out of the 20: tuning menu (second most common
complaint; no evidence yet that FM4's tuning code survives; check in
FB-12.0's string pass), debug menus (`forceEnableDebugMenus`, likely
compiled out), an E3 demo mode, the Forza 4 party modes (Car Soccer,
Bowling: code only, no ball or pin assets), tyre and fuel wear, the
offline Auction House (needs FB-7.3's server emulation), a randomizer
(after FB-12.2 and FB-12.3 exist), and a drag-and-drop in-game mod list
(FB-9.1; XE's crash reports show added cars need a check before loading).

ABI work that unlocks several rows: `call_guest_fp` (FB-12.7; FB-12.9 uses the native position descriptor),
HUD rectangles and images (FB-12.5 pages, lap deltas), vehicle-sim symbols
for speed, RPM and gear (FB-12.5, FB-6.2), and a built-in mod with
selectable variants (FB-12.6, FB-12.10, FB-12.16).

Working order: FB-12.0, then FB-12.1 to FB-12.3 from what it finds;
FB-12.4's spike in parallel because it can reopen split-screen; the data
mods (FB-12.6, FB-12.8, FB-12.10, FB-12.11, FB-12.16) as one built-in pack;
then `call_guest_fp` and FB-12.5, FB-12.7. FB-12.9 uses the native map
and position descriptor independently.

### FB-13 Custom content on top of the game

Analysis of 2026-10-11 at `dev` `a98998f`: what custom brands, cars, shops,
liveries, events and activities would take, from read-only reads of
`gamedb.slt`, the game's archives and executable strings, the DLC, XE and
Rally data, and a seed's save. Nothing was run in game; each issue names the
experiment that confirms it. Findings are in
[Cars, events and DLC](https://arcanite24.github.io/pinyon-shift/game-content/).

Most of FH1's content is data: cars, makes, parts, colours, events,
prizes, opponents and activities are database rows; routes, checkpoints,
shops and activities are plain XML; liveries are vector designs the game
renders. What the mod system lacks is adding *new* archive members and
string keys (FB-13.1), so that comes first, after a check of whether plain
text in name columns is enough. The online Storefront is not worth
emulating (no captured server replies); content is shared as mod packs and
files instead.

| ID | Content | Route | Effort | Confidence |
| --- | --- | --- | --- | --- |
| FB-13.1 | **Mod tooling: new archive members and string keys** ([#503](https://github.com/arcanite24/pinyon-shift/issues/503)) | Blocks most rows below; first check whether plain-text names work | M | Done (`95f806c3`): `add/` appends new members (stored, with the `0x1123` offset field) and `strings/<language or ALL>/<Table>.toml` adds `IDS_` keys to all three parts of a table; rebuilt tables are byte-identical. In game, a grading map added to `dynamicpost.zip` was used by the scene and a car bought in the Autoshow showed a name from a new `Data_Car` key (docs/MODDING.md). A new logo and decal are checked with FB-13.2 and FB-13.5, which add the data that references them |
| FB-13.2 | **Custom car brands** ([#504](https://github.com/arcanite24/pinyon-shift/issues/504)) | `List_CarMake` rows; the Autoshow make grid is one query; 37 dormant logos on the disc | S-M | Probable |
| FB-13.3 | **Clone cars: new ids on existing models with their own specs** ([#505](https://github.com/arcanite24/pinyon-shift/issues/505)) | About 47 car tables; Rally and XE precedent; a clone tool | S-M | Done: `tools/clone-fh1-car.py` (MODDING.md). Five clones (classes E to A) were bought in a chosen colour, driven, Auto Upgraded and kept after a reload, and the profile loads with the mod removed. The Autoshow lists the spec's index; the owned car shows the game's own, computed from its physics, so `pi` is set to that value and the tool no longer offers a weight scale (CurbWeight is not the game's weight) |
| FB-13.4 | **Custom dealers and shop locations** ([#506](https://github.com/arcanite24/pinyon-shift/issues/506)) | Shops are XML activities on `GameObjs` triggers; own car lists need an `IsCarVisible` hook; the online Storefront is XL and not recommended | S, L for own lists | Probable |
| FB-13.5 | **Custom liveries, decals and car skins** ([#507](https://github.com/arcanite24/pinyon-shift/issues/507)) | Liveries are encrypted vector `.liv` files in the save; decals by texture hash; skins by car texture; new decals and shapes need added members | S to L | Probable |
| FB-13.6 | **Import FM4 vinyl groups** ([#508](https://github.com/arcanite24/pinyon-shift/issues/508)) | The game's own cross-title importer; FM4 is an alternate title id; the SDK enumerates alternate titles | S-M | Probable |
| FB-13.7 | **Custom event packs** ([#509](https://github.com/arcanite24/pinyon-shift/issues/509)) | Events, routes with checkpoints, opponents, prizes and entry activities are data; a pack format with stable id allocation | S-M, L-XL for championships | Probable (Rally) |
| FB-13.8 | **Unused event types** ([#510](https://github.com/arcanite24/pinyon-shift/issues/510)) | Elimination mode 4 unused; drag, drift and autocross scoring from Forza 4 | S to L | Probable to guess |
| FB-13.9 | **Custom free-roam activities** ([#511](https://github.com/arcanite24/pinyon-shift/issues/511)) | Speed traps, stunts, photo shoots, barn finds and head-to-head drivers are XML and database rows | S-M each | Probable |
| FB-13.10 | **Custom upgrade parts, rims and paints** ([#512](https://github.com/arcanite24/pinyon-shift/issues/512)) | `List_Upgrade*`, `List_Wheels`, `Combo_Colors`; no new part types (code enum) | S | Probable |

Working order: FB-13.1's plain-text check and FB-13.3 (clone cars) first,
since brands, dealers and barn finds need a car to show; then FB-13.2,
FB-13.7 tiers 1-2 and FB-13.9; FB-13.6 as a cheap experiment at any time.
Car models from other games are FB-12.21 (#496) and FB-12.24 (#501).

### FB-14 What the native renderer makes possible

Research of 2026-10-11: features the FH1 Vulkan renderer (`Fh1NativeExecutor`)
allows that Xenos emulation did not. The renderer recognises render targets
(the scene, depth, the shadow mask, the sun shadow map and the HUD
boundary), not what each draw is, so features that need to tell cars, sky,
terrain or materials apart stay expensive. Draw distance is a guest problem
(the game culls before it submits), and ray tracing, screen-space
reflections and new materials have no inputs (no G-buffer or material ids).
Frame generation is planned since this round, opt-in (FB-14.6 to FB-14.9).
FB-14.6 to FB-14.9 are planned in detail in
[UPSCALING_BACKLOG.md](UPSCALING_BACKLOG.md) (UP) since 2026-10-16.

| ID | Feature | Effort | Confidence |
| --- | --- | --- | --- |
| FB-14.1 | **Texture packs on the Vulkan renderer (bug; FB-5.6)** ([#518](https://github.com/arcanite24/pinyon-shift/issues/518)) | S-M | Done |
| FB-14.2 | **Screenshots without the HUD and a HUD toggle key** ([#519](https://github.com/arcanite24/pinyon-shift/issues/519)). F2 (`bind_hud`, setting `hud_hidden`) holds the game's own HUD-hidden byte, so F8 photos and any capture tool get the frame without the HUD at no render cost; menus and photo mode still draw ([UI, HUD and input](https://arcanite24.github.io/pinyon-shift/game-ui/#hud-and-map)). The pre-HUD snapshot was not needed | S | Done |
| FB-14.3 | **HUD scale and safe-zone setting** ([#520](https://github.com/arcanite24/pinyon-shift/issues/520)) | S-M | Done: F6 > DISPLAY > HUD, HUD draws scaled through the viewport (`fh1_hud_scale`, `fh1_hud_safe_zone`) |
| FB-14.4 | **Colour grading mods: grading maps and a host LUT** ([#521](https://github.com/arcanite24/pinyon-shift/issues/521)) | S | Done: grading maps by mod (MODDING.md), `.cube` LUT on the scene (F6 > GRAPHICS > COLOUR LUT) |
| FB-14.5 | **Shader replacement as a mod folder** ([#522](https://github.com/arcanite24/pinyon-shift/issues/522)) | S-M | Confirmed hook |
| FB-14.6 | **Temporal upscaling and frame generation inputs, FSR 3.1 first (DR-5.4)** ([#523](https://github.com/arcanite24/pinyon-shift/issues/523)) | L | Probable |
| FB-14.7 | **FSR 4 upscaling and frame generation** ([#524](https://github.com/arcanite24/pinyon-shift/issues/524)) | M after FB-14.6 | Probable |
| FB-14.8 | **DLSS upscaling and frame generation from a player-supplied DLL** ([#525](https://github.com/arcanite24/pinyon-shift/issues/525)) | M after FB-14.6 | Probable |
| FB-14.9 | **Lossless Scaling frame generation from the player's own `Lossless.dll`** ([#526](https://github.com/arcanite24/pinyon-shift/issues/526)) | M | Probable |
| FB-14.10 | **Resolution scale per render target: shadows, post, reflections (FB-5.1, DR-2.1)** ([#527](https://github.com/arcanite24/pinyon-shift/issues/527)) | L | Probable |
| FB-14.11 | **Anti-aliasing and anisotropic filtering on the scene only** ([#528](https://github.com/arcanite24/pinyon-shift/issues/528)) | S-M | Done: FXAA on the scene (`swap_post_effect_scene_only`), anisotropy and LOD bias off depth-only and HUD draws. Measured on the RTX 4080 at 3x, uncapped, toggled within one free-roam route: median frame 8.96 ms with no AA, 9.10 ms with scene-only FXAA, 8.89 ms with FXAA over the HUD, 9.06 ms with scene-only FXAA and a LUT; filtering kept off depth and HUD draws at 16x, 9.00 ms against 8.95 ms before. All within run noise (about 0.15 ms). SMAA not added: scene-only FXAA already keeps the HUD sharp, and SMAA needs its area and search lookup textures and two more passes |
| FB-14.12 | **Frame inspector for modders and developers** ([#529](https://github.com/arcanite24/pinyon-shift/issues/529)) | S-M | High |

Working order: FB-14.1, FB-14.2, FB-14.3, FB-14.4, FB-14.5, then FB-14.6
stage 1, whose inputs feed FB-14.7 and FB-14.8; FB-14.9 needs only the
composed frames. FB-14.10 unlocks shadow resolution, 1x post at high scales
and photo mode at a higher scale.

## Not to build

- **Weather.** FH1 has no rain or snow assets, shaders or simulation, even in
  Rally; adding it is new content, not restoration. Confirmed again
  2026-10-11: the only wet strings are tyre friction scales, and
  `realtimesky.zip` holds one cloud set.
- **Split-screen as new work.** FH1 shipped none, and it means two
  open-world renders. Its code survives, though (FB-12.4): revisit only if
  that spike shows it running.
- **Connecting to Xbox LIVE or Forza services**, or anything presented as
  them. Replacements are local or self-hosted under the project's name.
- **Shipping game content**: music, cars, liveries or captured server data.

## Risks and open questions

| Risk | Settled by |
| --- | --- |
| The radio bank is not MPEG after all, or has an unknown layout | FB-1.3's byte-identical round trip |
| The guest ignores the system-player notification | FB-1.1; FB-1.4 does not depend on it |
| The vibration-level stub zeroes wheel FFB | FB-2.1 |
| No wheel in the project | FB-2.5 (a person); FB-2.1-2.3 progress with a virtual device |
| More LOD exhausts the 512 MB guest memory | FB-4.4 before FB-4.2 ships |
| Rivals and Storefront formats need server responses nobody captured | FB-6.1 and FB-7.2 work from what the client writes locally |
| Multiplayer physics desyncs at decoupled frame rates | FB-8.2's go or no-go |

## Working order

1. **Now:** FB-0.1, FB-0.2 and FB-0.4; FB-1.1 and FB-1.3 (cheap, decide the
   radio approach); FB-4.1 (S spike) and FB-4.5's A/B capture.
2. **Next:** FB-1.2, FB-1.4 to FB-1.7 (ship custom radio); FB-2.1 in parallel.
3. **Then:** FB-2.2 to FB-2.4 and FB-3.1 to FB-3.3 as one input project;
   FB-4.2 to FB-4.4; FB-0.3.
4. **After:** FB-6.1 to FB-6.3, FB-9.1 to FB-9.3, FB-7.1 and FB-7.2, FB-10.
5. **Research track:** FB-8.1 and FB-8.2; FB-5.1 to FB-5.3; FB-6.4 and
   FB-7.3 only with their prerequisites done.

## Needs a person

| Item | What | Who |
| --- | --- | --- |
| FB-1 gate | Listening to custom stations: transitions, DJ lines, levels | The maintainer |
| FB-2.5 | Wheels from at least two brands; FFB feel | Whoever holds the devices |
| FB-3.2, FB-3.3, FB-3.6 | DualSense, Switch Pro and Steam Deck | Whoever holds the devices |
| FB-4.2 | Judging pop-in against the original | The maintainer |
| FB-5.3 | An HDR display | Whoever holds one |
| FB-8.3 | Two machines and players | The maintainer and testers |

## Progress

Rows are added here as items are measured or done.

| Item | Status | Evidence |
| --- | --- | --- |
| Research | Done (2026-10-07) | Inventory of shipped features and open items, web survey, guest feasibility study; summarised above |
