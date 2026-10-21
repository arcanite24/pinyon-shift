# Changelog

## 0.6.1 - 2026-10-21

- Builds again on Linux and Steam Deck in folders with spaces (#727) and
  with FidelityFX on SteamOS (#681); Android APKs build from the release
  source (#716) and after a stopped build (#763).
- Setup fetches AMD's FidelityFX and NVIDIA's DLSS runtimes on Windows;
  the upscaler setting names FSR 1 when the chosen one can't run (#762,
  #670).
- Racing wheel force feedback and a launcher wheel screen (#337); fuller
  telemetry with the Forza Horizon 4/5 layout as an option.
- WINDOWS HDR switch, live chase camera tuning (#487) and the immersive
  camera on v4, trainer road travel and GPS (#485), shader replacement
  mods (#522), a frame inspector (#529), and an Android opt-in for Mali
  GPUs.
- Fixed: shadows-off garage photos (#700, #733), textures after livery
  edits (#628), hidden cars for sale (#669), settings written by a mod
  builder, older Apple clang (#775).
- Faster: no double presents with overlays open and no per-frame GPU wait
  for exposure.

## 0.6.0 - 2026-10-17

- Temporal FSR 2 and FSR 3 in OUTPUT SCALING, fed with depth, camera and
  object motion, a jittered scene and a HUD-less frame; SHARPENING; motion
  blur and depth of field off under them. FidelityFX builds from source on
  Linux, macOS and Android; Windows needs AMD's runtime beside the game.
- DualSense adaptive triggers, lightbar, player lights, tilt steering and
  PlayStation button marks (#561); racing wheel steering and pedal shaping.
- Ultra Low 30 preset, TEXTURE SIZE cap, FXAA on the world only (#528),
  COLOUR LUT (#521), HUD SCALE and SAFE ZONE (#520), F2 hides the HUD
  (#519).
- SKIP INTRO MOVIES and START IN SINGLE PLAYER (#617), developer-build
  switches (#477), photo camera through walls and wider limits (#488), AI
  without rubber-banding or one level harder (#482), trainer DAY LENGTH
  (#483) and ANY CAR IN ANY EVENT (#479).
- Sound mixer per category with the compressor on or off (#486).
- Car telemetry over UDP in Forza Motorsport 7's Data Out layout (#481).
- Texture packs on Vulkan (#518), hidden traffic and showcase cars for sale
  (#484), cars reusing an existing model (#505), new archive members and
  string table keys (#503).
- Every Windows launcher panel on Linux and macOS, including DLC, title
  update v4 and Xenia save import.
- Android: mods, radio and XE in the Wi-Fi share, APK updates offered by
  the app, and a shader-pack command.
- Faster: CTR, XER and LR in locals, host fibers, literal folding and direct
  strong-body calls in the recompiled code; FMOD output without the guest
  XAudio2 pass, native ParamEQ, worker XMA decoding, FMOD stereo on Android
  and Linux; shader-load cache; parallel pipeline builds and an off-thread
  pipeline cache save; indexed v4 car restrictions; Deck x86-64-v3, small
  code model and thread placement; macOS 120 Hz defaults and no black
  screen while pipelines compile.
- Fixed: white window without `gpu_backend` (#627, #613), judder at a
  steady frame rate (#381), controllers routed to user 0 (#553), headlights
  at night with shadows off (#532), macOS resize black screen (#623, #475,
  #578), overbright free roam and launcher crashes on macOS, crashes (#584,
  #638, #552), a newer settings file (#536), Xenia DLC folders (#596), the
  damaged Rally dump (#573, #610), the v4 save hint (#555), and setup
  (#599, #639, #604, #580, #597, #560, #574, #567, #649, #616, #624),
  launcher scaling (#594).
- Crash reports name the faulting module and driver and say when the GPU
  driver or graphics memory was the cause (#558); the build label shows in
  the title and F3 (#545).

## 0.5.1 - 2026-10-12

- VSYNC on no longer tears on Vulkan, and changing it applies at once (#539).
- Start laptops on the high-performance GPU (#534).
- Setup: start the Build Tools installer once, report a failed repair's
  own error (#458, #533, #498, #502), work without `ComSpec` (#541), check
  non-reference disc images file by file (#462), count macOS purgeable
  space (#461), and build on Linux with libxml2 2.14 or newer (#472, #474,
  #514).
- Build the title update v4 from a release install on the first try
  (#459, #540).
- Package the Android build when the user folder's path is long or has a
  space (#538), and show HDR10 correctly on the Odin 2 Portal (#500).
- Native replacements for `pow`, the LZX decoder and the render thread's
  idle wait, with each checked against the game's code; condition flags in
  locals and direct stack accesses in the recompiled code; event-driven
  waits on Android, Linux and macOS.
- Pick the bundled Turnip gen8 v37 driver on Adreno 8xx, as on 7xx.
- Log settings changes in the session log (#542).

## 0.5.0 - 2026-10-11

- Built natively for Linux and the Steam Deck (not Proton), with a Linux
  launcher archive and Add to Steam; 60 fps at 1x on the Deck at 15 W.
- Built natively for Apple silicon Macs, with Vulkan on Metal through
  MoltenVK and a macOS launcher app.
- Installed the Android alpha over Wi-Fi from the launcher's Android panel,
  without adb, and renamed its package to `studio.deimos.pinyonshift`
  (`pinyon.py android migrate` moves an earlier install).
- Imported DLC from the player's own Xbox 360 packages, and added the
  optional title update v4 build for the original Horizon Rally and the
  1000 Club challenges offline (Windows and Android).
- Drove on WASD by default, rebound keys and mapped controllers in game,
  and opened the settings with a controller chord.
- Started new installs at the Low-spec 60 preset, added Balanced 40, and
  recommended a preset for the PC in the launcher.
- Imported Xenia saves under their profile and accepted verified extracted
  game folders.
- Steam Deck and Linux: about 3 % faster rendering by default, and a new
  F6 > GRAPHICS > SCENE SHADING > COARSE that shades once per 2 x 2
  pixels for about 8 % more on the Deck, a little softer (#427).
- Expose the screen correctly at any time of day above 1x resolution;
  mornings were overexposed until about noon in game (#444).
- Make up to three radio stations from your own music in the launcher's
  Radio panel, each with its own name, logo and songs in place of Bass
  Arena, Pulse or Rocks, adding to or replacing the playlist (#445).
- YOUR MUSIC plays only once the festival has loaded; the title screen
  keeps the game's own music (#445).
- HDR output: richer colors (gamma 2.2 decode), softer highlights
  (HDR HIGHLIGHTS), brake lights expanded with their hue, no flicker on
  translucent HUD. HDR now switches without a restart, HDR COMPARE shows
  SDR and HDR side by side, and HDR CALIBRATION sets the paper white
  and the display's peak from test patterns (#442).
- The launchers' Logs link opens the game's own logs (runtime.log)
  once it has run, instead of the setup logs (#424).
- Update from inside the launcher: **Update to <version>** downloads the
  newer GitHub release, checks its SHA-256, replaces the launcher and
  restarts, keeping saves, settings and game files. Works on Windows,
  Linux and macOS and in portable installs; `PINYON_SHIFT_UPDATE_CHECK=0`
  turns the check off.
- Offer the optional immersive camera on F6 > DISPLAY (#419), with
  SUBTLE, DEFAULT and STRONG presets and G-force, lean, speed shake and
  head motion rows, all applied without a restart (#443).
- Start when the Windows user folder has an accent or other non-ASCII
  characters, such as C:\Users\Júnior; the game closed at once (#436).
- Build a radio station from a folder of music with
  `tools/build-fh1-radio.py`, as a mod that adds the tracks to Radio1-3
  or replaces a playlist (#420).
- Play your own MP3 and WAV files from the state's `music` folder (F6 >
  AUDIO > YOUR MUSIC, F9 and Shift+F9 to skip); the game silences its own
  music as under a 360 dashboard soundtrack (#420).
- Convert quad lists to triangle lists on every platform: about 3 % of
  the GPU's frame at 2x on an RTX 4080 and 5 % on an M4 Pro; offer
  TEXTURE GAMMA on desktop (#427).

- Install the Forza Horizon XE mod from the player's own ModDB downloads
  with `pinyon.py xe` or the launchers. XE runs on the base build with
  Horizon Rally hidden and plays its own new save; the player's save is kept.
- Let mods hide marketplace DLC (`hide_dlc`) and play their own save
  (`profile`); list a mod's new files with the disc's directories; build
  database and archive patches on top of a mod's replacement files.

- Default to bloom OFF with a live settings toggle. Suppress its contribution
  through the title's frame-local scale while preserving weather and tone mapping.
- Default to MSAA OFF on desktop and Android while preserving saved choices;
  changes still require a restart.

- Avoid racing active SDL threads during a fatal render-test rejection; flush
  the diagnostic failure before exiting immediately.

- Bind Rally stages to their owned ticket artwork through reserved base-UI
  texture names, fixing black cards in the native ticket prototype.

- Preserve unfinished Rally championships when a native event menu loads its
  selection; apply the same resume guard as named event entries.

- Apply each Rally championship's correct class target and the supported base
  class restriction to its stages; Rally upgrade eligibility remains pending.

- Correct Rally championship and stage names to match their owned routes;
  rebuild older prepared content without changing saves.

- Initialize Visual Studio builds when a portable launcher uses a temporary
  path containing parentheses; preserve its TEMP/TMP paths afterward.

- Preserve base route and region labels while adding owned Rally labels in
  all 20 languages during content preparation.

- Release the diagnostic Rally AI driver back to player control at stage end;
  verify the same car/race handoff and final-stage free-roam return.

- Require Visual Studio 2022 Build Tools 17.1 or newer during discovery, so
  VS 2019 cannot bypass provisioning and fail later on `std::byteswap`.

- Fixed Android MSAA and graphics presets failing to show that a restart is
  required. Settings now honor the SDK flag lifecycle metadata.
- Accepted Windows line endings in render-test scripts on Android and other
  platforms, including the schema header and clock directive.

- Replaced a startup crash from an unavailable saved Rally tyre with a recovery
  message. Re-enable or restore its DLC to keep driving with the purchased part;
  the save is preserved.
- Added Rally tyre conversions derived from the supported base-disc data when
  owned Rally content is enabled. A Mustang's normal purchase, save/reload and
  initial Rally driving pass; base-car suspension/transmission remain pending.

- Made Vulkan the sole supported graphics API. Direct3D 12 is legacy and
  unsupported; saved selections migrate to Vulkan and player settings no
  longer offer it.
- Fixed Custom Upgrade crashing after loading a saved car by initializing its
  native upgrade views when the car loads.
- Added the missing Rally tyre, suspension and transmission upgrade definitions
  to owned-content preparation on the base build, with Rally tyre parameters and
  English and Spanish menu text.
- Added an experimental Horizon Rally menu for owned content, with championship
  selection, resume status and retirement confirmation. Full Rally gameplay is
  still being qualified on the base-disc build.

## 0.4.0 - 2026-10-03

- Fixed Vulkan losing the GPU on AMD Radeon cards: the game could wait on a
  fence before it was submitted. Fixed three other Vulkan validation errors.
- Fixed green, white and pink blocks while shaders compile, a stop at guest
  address 0x38 with the Treasure Map, a setup compile error on some PCs, and
  a hang or crash when the render job queue overran during heavy frames.
- Played the start-line crowd and the car purchase cameras at console speed
  at 60 and 120 fps.
- Showed late frames as soon as they are ready, steadying 120 fps at 1x.
- Made 2x to 4x lighter on the GPU (compute texture loads, resolves written
  into the textures that read them) and the GPU recorder thread cheaper.
- Prepared Vulkan shaders during setup.
- Added Build Android APK to the launcher (alpha): the game cross-compiled
  for arm64 Android from the PC build, with touch controls and presets.
- Wrote the guest threads' stacks to the log when the game stops responding.

## 0.3.1 - 2026-10-01

- Fixed setup and launches with Direct3D 12 stopping while preparing graphics
  because the shader sources were looked up in a developer checkout's path.

## 0.3.0 - 2026-10-01

- Rendered the game with a native renderer for *Forza Horizon* on Vulkan (the
  default) or Direct3D 12, with shader packs prepared and repaired locally.
- Rendered at 60 or 120 fps with the simulation at the right speed, and at 1x
  to 4x internal resolution, changeable in game, with FSR 1 or CAS output
  scaling.
- Added in-game settings (F6 or the pause menu) for display, graphics, audio
  and controls, most applying at once, with Performance 120 and Quality 60
  presets.
- Added ultrawide Hor+ with a 16:9 HUD and a field of view setting, monitor,
  window size, aspect and frame-rate settings.
- Added a gamertag and picture, an achievements list, PNG photos, save
  backups, the disc's 18 languages, button remapping and mouse camera or
  steering.
- Added a trainer (credits, game speed, time of day, free camera, collectibles
  on the map) on a separate modded profile, and mods: native plugins, file,
  archive, database and texture replacement, text, HUD labels and menu
  actions.
- Included the Treasure Map add-on, on by default with a launcher toggle.
- Redesigned the launcher, added a Settings panel that shows the rendered and
  output resolutions, and portable installs.
- Made setup report the failed step and its first real error, retry locked
  runtime copies, start PowerShell by its full path, explain a declined
  administrator prompt, tolerate shader-pack misses on slower PCs, unpack the
  compiler with Windows' own tar and size the build's parallel jobs to memory.

## 0.1.1 - 2026-08-27

- Fixed launcher-package builds that completed translation but failed while
  probing absent Git metadata.
- Removed the packaged setup workflow's Python dependency by verifying codegen
  warnings with Windows PowerShell.

## 0.1.0 - 2026-08-26

- First Windows public playable preview.
- Updated the pinned ReXGlue SDK from 0.9.0 to 0.10.0, including its threading,
  audio, input, GPU, diagnostics, and incremental-codegen improvements, while
  preserving the project's runtime compatibility patch set.
- Added a graphical launcher that verifies a supported disc and performs the
  complete local toolchain, extraction, generation, and build workflow.
- Added reproducible dependency pins and a public-source repository boundary.
- Added resilient ReXGlue/submodule download retries, disabled SDL's optional
  libusb probe on Windows, and made Xbox menu acceptance accessible through
  Space or left click with an in-launcher control hint.
- Made launcher setup ignore quoted `PATH` entry syntax when initializing the
  Microsoft build environment and always use the verified pinned MinGit.
- Restored motion blur around the player car and removed the stale gameplay
  limitation list after the latest compatibility fixes.
- Added launcher controls for validated graphics experiments, including 2x
  resolution scaling, anisotropic filtering, and post-effect selection.
- Fixed launcher-package builds that completed translation but failed while
  probing absent Git metadata, and removed Python from warning verification.
- Added an experimental 3x internal-resolution preset for 4K-class output.
