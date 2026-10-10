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
| 4 | FB-4 Draw distance and world detail | Not requested, seen by everyone | S spike, M | LOD distances look data-driven |
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
| FB-0.3 | **Open rendering bugs players see first:** cutscene and wristband corruption (#356, NP-2.9), boot over-exposure (#380), post-race hitching (#381), DOF (GH-21). Fix or label each. | M | In progress: #381 measured 2026-10-10 (per-frame simulated time from the performance CSV, 120 fps limit, 2x): after a race is retired, 25-40 % of presented frames carry 0 or 16+ ms of simulation, against 3-17 % in the race and 7-27 % in free roam before it. The simulation's ticks fall in and out of phase with presents (0 or 2 ticks per present), which reads as hitching while the frame time stays flat; `pinyon_shift_host_simulation_delta=true` only reduces it to 16-29 %. No fix yet |
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
| FB-2.1 | **Guest wheel contract.** Report subtype 2 with the FFB flag from a test driver and trace `sub_8310C968`, the +4 and +4244 flags, which steering and filter path engages, and what the two motor values mean under a wheel (constant force? spring?). Check whether the ordinal-442 stub zeroes output. | S-M | Not started |
| FB-2.2 | **Wheel driver.** SDL3 joystick (not gamepad) devices with a wheel or user-chosen profile: steering, separate throttle, brake and clutch axes, H-pattern and sequential shifter buttons, mapped onto the guest's wheel state with subtype 2. DirectInput only if SDL misses devices FB-2.4 needs. | M | Not started |
| FB-2.3 | **Force feedback.** Translate the guest's motor values into an SDL haptic constant-force effect on `SDL_HAPTIC_STEERING_AXIS`, with host spring and damper scaled by the values in `ControllerFFB.ini`. Then decide whether to recreate the ini's model host-side from the car's self-aligning torque (L). | M-L | Not started |
| FB-2.4 | **Settings.** A WHEEL page in F6: rotation, steering linearity and deadzone, pedal curves and inversion, combined or separate pedals, FFB gain and centring, a calibration step, and per-device profiles. | S-M | Not started |
| FB-2.5 | **Device matrix.** Logitech (G29/G920/G923), Thrustmaster (T300/T150/TMX), Fanatec, Moza; Windows and Linux (kernel quirks such as Moza's FIX_WHEEL_DIRECTION). Record each in a tested-hardware table. Closes GH-9 and #337. | M | Needs a person |

### FB-3 Controller extras (S-M)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-3.1 | **Stick deadzones and response curves** on the host (none today: `sdl_input_driver.cpp:495-590` passes axes raw), per stick and trigger, with a test view in F6. | S | Not started |
| FB-3.2 | **Gyro steering** for DualSense, DualShock 4 and Switch Pro: `SDL_SetGamepadSensorEnabled`, blend into left-stick X with recentre and sensitivity. | S-M | Not started |
| FB-3.3 | **Trigger rumble and adaptive triggers.** `SDL_RumbleGamepadTriggers` for Xbox controllers; DualSense resistance through `SDL_SendGamepadEffect`, derived from throttle and brake input plus the guest's motor values (the guest exposes nothing trigger-specific, so this is an approximation). | M | Not started |
| FB-3.4 | **In-menu keyboard binding editor** and analog ramp for keyboard steering and throttle (NP-6.1). | S-M | Editor done (#401): choosing a key row in F6 > CONTROLS asks for a key or mouse button, which replaces the row's keys and applies at once; RESET KEYS restores the defaults. The analog ramp is not started |
| FB-3.5 | **Button glyphs per device** in host UI; guest HUD glyphs stay Xbox (NP-6.2). | S | Not started |
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
| FB-4.1 | **Find the keys.** Decompress `renderscenarios.zip` with `tools/patch-fh1-archive.py`'s reader, locate each key above in data or code, and record which are loaded from files and which are constants. Trace which scenario free roam selects. | S | In progress: scenario keys read (above). Probed 2026-10-10 with changed copies of the archive: race scenarios apply (`Horizon_Race.xml`'s car LOD changed race-ready cars), but free roam reads none of the 35 files, `Global.xml` included, so its car LOD is set in code. Grass, terrain, `CamFarClip`, `SLod.xml` and the free-roam code path remain |
| FB-4.5 | **Photo mode detail in gameplay.** A setting that applies `PhotoMode.xml`'s detail keys (`CarMinWheelLOD 0`, `CollidableShadows 1`, `SoftParticles 1`, not its DOF change) to every scenario through XML merges. Trace what the code does on `IRenderThreadInPhotoModeInternal` and `IPresentationInPhotoMode`, and the `highrescubemap` option, for quality switches that are not in data. Photo capture's accumulation supersampling (`MultiSampleAndAccumulate`, `AccumulateWeightedFrame`) and BIG SHOT need a still scene and are not real-time features; the resolution scale is their real-time counterpart. Gate: a visible difference in an A/B capture, then cost measured on the race. | S-M | Not started |
| FB-4.2 | **World detail preset.** A WORLD DETAIL setting (ORIGINAL, HIGH, ULTRA) that raises car, crowd, grass and traffic LOD distances and far clip through XML merges or a host hook; measure CPU, GPU and guest memory per step. | M | Not started |
| FB-4.3 | **Traffic and crowd density** as separate options, shared with LS's "optional reductions to game systems" so the same setting lowers them on weak machines. | M | Not started |
| FB-4.4 | **Memory ceiling.** Measure guest heap headroom in the worst scenario (16-car race, Autoshow) and stop the preset before it. | S | Not started |

### FB-5 Image quality beyond the console (M-L each)

| ID | Item | Effort | Status |
| --- | --- | --- | --- |
| FB-5.1 | **Shadow resolution apart from internal scale.** Override the shadow-map targets and viewports for those passes only in the native executor (cascades are set in shaders, `CSMShadowMapLevel0TM`). Fix NP-4.10's 2x-4x shadow artifacts first. | L | Not started |
| FB-5.2 | **Reflections.** Raise the dynamic cubemap's size or update rate (`DynamicCubemap`, `EnvMapFrequencyScale`), from data if FB-4.1 finds it, otherwise in the executor. | M-L | Not started |
| FB-5.3 | **HDR output.** The presenter only selects sRGB swapchains (`src/ui/vulkan/vulkan_presenter.cpp:1258-1293`) and the guest tonemaps to SDR; take the scene before the tonemap and add HDR10 or scRGB presentation (NP-4.8: plumbing M, quality L). | L | Not started |
| FB-5.4 | **Upscaling and AA.** FSR 1 quality presets and sharpness (README "next"), temporal upscaling (DR-5.4, researched), non-integer scale (NP-4.8). Tracked there. | - | Pointer |
| FB-5.5 | **Modern bloom, motion blur and DOF** (LS "Requested defaults"). Tracked there. | - | Pointer |
| FB-5.6 | **Texture packs on Vulkan.** Confirm the Vulkan path honours `texture_replacement_dirs` (the cvar is defined in the D3D12 texture cache) and fix if not. | S | Not started |

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
| FB-10.1 | **Trainer v2**: freeze and teleport (blocked on the physics body, NP-8.1), unlock cars and events, any car in any event, remove car limits (NP-8.5-8.7). | M | Pointer |
| FB-10.2 | **AI driving for the player's car** in the trainer, reused by automated routes (README mid term). | M-L | Not started |
| FB-10.3 | **Photo mode upgrades**: free camera with field of view, roll, depth of field and HUD hidden, writing through photo export. | M | Not started |
| FB-10.4 | **Shorter loading and transitions** (README mid term; PB owns measurement). | L | Pointer |
| FB-10.5 | **Accessibility**: HUD and subtitle scale, colour filters, hold-to-toggle inputs (NP parking lot). | M | Not started |
| FB-10.6 | **Discord rich presence** (NP parking lot): current event, car and area. | S | Not started |
| FB-10.7 | **Update from inside the launcher**, keeping saves and settings (README next). | M | Not started |

### FB-11 Platforms (pointers)

| ID | Item | Owner |
| --- | --- | --- |
| FB-11.1 | Linux build and launcher (never configured on Linux yet; one player runs the Windows build under GE-Proton, #388) | NP-12.1, 12.2, 12.7 |
| FB-11.2 | Steam Deck qualification: gamescope, 1280x800, Steam Input, suspend and resume | NP-12.8, LS-0.1 |
| FB-11.3 | macOS through MoltenVK | NP-13 |
| FB-11.4 | Android install and sustained performance | AP, A60 |
| FB-11.5 | Nintendo Switch feasibility | ROADMAP_FEEDBACK |

## Not to build

- **Weather.** FH1 has no rain or snow assets, shaders or simulation, even in
  Rally; adding it is new content, not restoration.
- **Split-screen.** FH1 shipped none, and it means two open-world renders.
- **Frame generation.** Already rejected (config migration removes it).
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
