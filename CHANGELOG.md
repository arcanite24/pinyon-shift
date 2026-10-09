# Changelog

## Unreleased

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
