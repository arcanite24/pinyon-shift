# Roadmap

Public priorities, updated 2026-10-13 from community feedback and the current
development work. Gameplay-blocking bugs and save safety take priority within
each phase. These are priorities, not release dates; ports need validation on
their target hardware before they are ready for players.

The [community request review](ROADMAP_FEEDBACK.md) explains the demand and
the proposed additions. The [feature backlog](FEATURE_BACKLOG.md) is the
central list of player-facing features. Implementation details and acceptance
gates are in the
[native port backlog](NATIVE_PORT_BACKLOG.md),
[performance backlog](PERFORMANCE_BACKLOG.md) and
[Android port backlog](ANDROID_PORT_BACKLOG.md).

Done since 0.1:

- [x] Change resolution and render scale while the game is running
- [x] Apply graphics settings without restarting the preview
- [x] Support ultrawide (21:9 and wider) displays, with a 16:9 HUD and a field
  of view setting
- [x] Ship a modding API for loading custom content: native plugins, file and
  archive overrides, database patches and texture replacement
- [x] Let mods add HUD labels, menu actions and replacement text
- [x] Play in any of the disc's 18 languages
- [x] Achievements, photo export, save backups and a trainer in game
- [x] Support portable installs
- [x] Keep crowd and purchase animations at the right speed above 30 fps
- [x] Initial Android runtime and local APK build from the launcher
  ([developer alpha](ANDROID.md))
- [x] 60 fps on Snapdragon 8 Gen 2 handhelds, a bundled Turnip driver and
  custom GPU driver import on Android
- [x] One-click setup: nothing to install by hand on Windows, and Android
  installed over Wi-Fi without adb
  ([backlog](ONE_CLICK_SETUP_BACKLOG.md))
- [x] Native Linux and Steam Deck support: a launcher for Linux, Add to
  Steam, 60 fps on the Deck ([Linux and Steam Deck](LINUX.md))
- [x] macOS on Apple silicon, with Vulkan on Metal through MoltenVK
  ([macOS](MACOS.md))
- [x] FH1 v4 title-update support, built from your USA disc and your own
  update: Horizon Rally and 1000 Club run their original code, 1000 Club
  offline ([title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md))
- [x] DLC support from your own Xbox 360 content: every car pack, VIP and
  the expansions ([below](#dlc-packages))
- [x] Update from inside the launcher while preserving saves and settings
- [x] HDR output, with calibration, a side-by-side comparison and a runtime
  toggle (#417, #442)
- [x] An optional immersive camera: G-forces, lean, speed shake and head
  motion, with presets (#419, #443)
- [x] Your own music in game, and custom radio stations with their own name,
  logo and songs, managed from the launcher (#420, #445)
- [x] Install the Forza Horizon XE mod from your own ModDB downloads, playing
  its own save (#426)
- [x] Keyboard rebinding and a controller mapping assistant (#401, #432)
- [x] Setup that needs only the launcher zip and your dump: free space,
  download sites, the Vulkan driver and the install path checked up front,
  Visual Studio repaired, and setup resumed after a required restart (#393)
- [x] Vulkan as the single supported renderer on every platform, lighter at
  2x to 4x internal resolution

In progress:

- [ ] Main focus: bring the CPU and memory cost close to a native build of
  FH1, measured on the Odin 2 Portal and the Steam Deck, by replacing
  emulated layers (the GPU command front end, the audio path, kernel
  objects) and translation overhead
  ([near-native research](NEAR_NATIVE_RESEARCH.md))
- [ ] Fix remaining crashes, loading failures, rendering regressions and
  recurring stutter: hills seen through (#424), hitching (#381), frame drops
  in free roam (#416), resuming after quitting before the first festival
  event (#447), the trainer not opening (#450) and the Steam Deck settings
  menu (#429)
- [ ] Faster Android rendering on tiled GPUs (#414), and the Odin's GPU
  savings measured on desktop, the Steam Deck and macOS (#427)
- [ ] Hand-optimize the hottest recompiled guest functions (#431)
- [ ] Document FH1's guest code in a symbol database
  ([reverse-engineering records](https://arcanite24.github.io/pinyon-shift/reverse-engineering/), #448)

Next, in priority order:

- [ ] Qualify AMD and Intel GPUs, including low-end integrated graphics
  (#388), and publish tested hardware, drivers, settings and performance
  results
- [ ] Draw distance and world detail settings (#421), and an atmosphere and
  effects pack: clouds, fog, particles and backfire (#422)
- [ ] Expose FSR 1 quality presets and sharpening controls in settings,
  with the rendered and output resolutions shown clearly
- [ ] Validate Steam Deck and SteamOS: controls, Steam Input, suspend and
  resume, and performance presets
- [ ] Improve sustained Android frame pacing and thermals on supported
  devices; measure long sessions as well as startup performance
- [ ] Safely import saves from Xenia and Xbox 360, and transfer profiles
  between supported platforms
- [ ] Support more disc regions
- [ ] A feature comparison table on the website, by platform and against the
  original (#455)

Mid term, in priority order:

- [ ] Add radio stations alongside the stock ones instead of replacing them
  (#453), with a logo preview, a playlist editor and YouTube sources in the
  launcher (#454)
- [ ] Export your own game files to standard formats from the launcher:
  audio, textures, models, strings and data (#446)
- [ ] Let the trainer toggle AI driving for the player's own car, with an
  immediate return to manual control
- [ ] Reuse player-car AI driving in automated gameplay and performance tests
  from pinned save seeds, with route checks and captured diagnostics
- [ ] Improve asset streaming and multi-core utilisation; replace measured
  bottlenecks and fixed limits inherited from Xbox 360 hardware
- [ ] Shorten loading screens and remove avoidable loading transitions through
  background streaming; speed up saves while preserving atomic writes and backups
- [ ] Better Android performance on lower-end hardware, with published
  device requirements and sustainable graphics presets
- [ ] An Android launcher that builds the game on the device, without a PC
  (#451)
- [ ] Nintendo Switch support, starting with hardware feasibility and
  performance validation
- [ ] Racing wheel, pedal and force feedback support (built: the game's
  wheel mode, clutch, H-shifter and force feedback, tested on one wheel;
  open: more wheels and Linux, FB-2.5)
- [ ] Install, enable and order any mod from the launcher, with compatibility
  guidance for existing FH1 mods
- [ ] Verify DualSense and variable refresh rate displays
- [ ] Sign the launcher and preview executables

Longer term and research:

- [ ] Hold 120 fps in every race, and pursue 4K at 120 fps on qualified hardware
- [ ] More trainer options: unlock cars and events, and let any car enter any
  event
- [ ] Let mods add items to the game's own menus
- [ ] Import cars from *Forza Horizon 2*
- [ ] Research importing cars from *Assetto Corsa*, including geometry,
  materials, physics and FH1 integration for compatible, permitted content
- [ ] Investigate multiplayer restoration, starting with LAN feasibility

Other *Forza* recompilations would be separate projects; stabilising FH1
comes first.

Measured findings and validation rules are in
[development findings and priorities](DEVELOPMENT.md).

## DLC support today

- **Import.** `tools/manage-fh1-dlc.py` (and the launcher) verify your own
  packages against a pinned catalog of 21 FH1 packages and import them. Each
  package is enabled separately. This covers Rally, 1000 Club, the monthly
  car packs, VIP, Honda, the pre-order and the single cars.
- **Rally on the base disc.** A prepared overlay makes the championships
  playable from F6. Stage records, pace notes and resume are saved, but the
  original in-game entry is not restored yet.
- **Rally and 1000 Club on v4.** The optional v4 build runs the expansions'
  original code. It is built from your disc and your own v4 update, on
  Windows (`tools/build-v4.ps1`) or Android (`--title-update-v4`). 1000 Club
  runs offline when its launcher option is on. A save written by v4 cannot go
  back to the base build, so the launcher backs it up first.
- **Car packs.** Qualified with every owned package enabled together (on the
  optional v4 build, and spot-checked on the default build): each pack's cars
  are owned in the game's own entitlement cache and show in the Autoshow, and
  one car per pack was bought, reloaded from a fresh launch and driven. Import
  every copy of a package you own: verified variants of the same package
  combine their licences (the full November pack needs its full-licence copy).

## DLC packages

- [x] Treasure Map functionality, already included in the preview
- [x] Launcher DLC import, detection and enable/disable controls
- [x] Horizon Rally Expansion Pack: native entry, intro, hub, car selection and
  a championship on the v4 build (other championships not yet played)
- [x] 1000 Club Expansion Pack: offline car challenges with saved medals on the
  v4 build ("1000 Club offline" in the launcher)
- [x] October Car Pack
- [x] November Bondurant Car Pack
- [x] December IGN Car Pack
- [x] January Recaro Car Pack
- [x] February Jalopnik Car Pack
- [x] March Meguiar's Car Pack
- [x] April TopGear Car Pack
- [x] VIP Membership & Cars Pack: cars, plus Fast Travel Anywhere on v4
- [x] Honda Challenge Car Pack (cars; the challenge flow is unqualified)
- [x] Pre-Order Car Pack
- [x] Season Pass: 2006 Lamborghini Miura Concept
- [x] 2013 Ford Shelby GT500 - Rockstar Energy
- [x] Individual promotional cars: Nissan 370Z, Ferrari 458 Italia,
  Mercedes-Benz SLS AMG, Volkswagen Golf R and Aston Martin Virage (they share
  the Pre-Order cars without duplicates)
- [x] LCE: Day1 DLC Pack, including its custom-painted cars (shares the
  October roster)

Detailed status, dependencies and acceptance checks for each package are in
the [DLC backlog](DLC_BACKLOG.md).
