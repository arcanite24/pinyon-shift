---
title: Settings and controls
section: Playing
order: 1
description: Keyboard shortcuts, graphics presets, language, controllers, saves and photos in Pinyon Shift.
---

# Settings and controls

Most settings live in the game, on <kbd>F6</kbd>, and apply at once. MSAA and the language are among the few that need a restart.

## Keys

| Key | Action |
| --- | --- |
| <kbd>F6</kbd> | Settings. Also **SETTINGS** in the pause menu |
| <kbd>F3</kbd> | Performance panel, with the build line (version, commits, build time) to quote in a bug report |
| <kbd>F7</kbd> | Achievements |
| <kbd>F2</kbd> | Hide or show the HUD (minimap, speedometer, banners), for screenshots. Menus and photo mode still draw |
| <kbd>F8</kbd> | Save the current frame as a PNG photo |
| <kbd>F10</kbd> | [Trainer](#trainer): credits, game speed, time of day and day length, free camera, any car in any event. Needs cheats on |
| <kbd>F11</kbd> | Fullscreen. Also <kbd>Alt</kbd>+<kbd>Enter</kbd> |

On a Mac, where the F-keys are media keys, use <kbd>Cmd</kbd>+<kbd>,</kbd> for the settings, <kbd>Ctrl</kbd>+<kbd>Cmd</kbd>+<kbd>F</kbd> for fullscreen, <kbd>Cmd</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> for a photo, <kbd>Cmd</kbd>+<kbd>T</kbd> for the trainer and <kbd>Cmd</kbd>+<kbd>Q</kbd> to quit.

Mac fullscreen uses a borderless window on the current desktop. If an older
build turns black when changing fullscreen, rebuild; the presenter now keeps
the Metal drawable at the window's swapchain size. The visible result still
needs checking on other Macs ([macOS qualification](platforms.md#macos-on-apple-silicon)).

On a controller, hold **Back + Start** together (View + Menu on a Steam Deck) to open the settings, and **LS + RS** for the performance panel; both chords can be changed in **F6 > CONTROLS > CONTROLLER**.

### Driving on a keyboard

| Key | Control |
| --- | --- |
| <kbd>W</kbd> / <kbd>S</kbd> | Throttle / brake |
| <kbd>A</kbd> <kbd>D</kbd> or <kbd>←</kbd> <kbd>→</kbd> | Steer. The arrows also move through menus |
| <kbd>Space</kbd> | Handbrake; accept in menus (also <kbd>Enter</kbd> or a left click) |
| <kbd>E</kbd> / <kbd>Q</kbd> | Shift up / down. <kbd>E</kbd> and <kbd>Backspace</kbd> are also B (back) |
| <kbd>R</kbd> | Rewind |
| <kbd>C</kbd> | Camera |
| <kbd>Z</kbd> | Clutch |
| <kbd>I</kbd> <kbd>J</kbd> <kbd>K</kbd> <kbd>L</kbd> | Look around |
| <kbd>Tab</kbd> or <kbd>M</kbd> / <kbd>Esc</kbd> | Back / Start (pause) |
| <kbd>Shift</kbd>+arrows | D-pad |

Keys can be rebound in **F6 > CONTROLS**, and **RESET KEYS** returns to this layout. An install from before this layout keeps the keys it had until then.

## Graphics presets

| Preset | Resolution | MSAA | Output | Rate | Notes |
| --- | --- | --- | --- | ---: | --- |
| Ultra Low 30 | 1x | Off | Bilinear | 30 | For integrated graphics on 2 CPU cores, which the launcher recommends it for. As Low-spec 60 without the sun's shadows, with the car reflections updated at a quarter rate, the scene drawn in one pass and textures at most 256 texels across, at the console's own 30 fps. Choosing another preset turns these back on |
| Low-spec 60 | 1x | Off | Bilinear | 60 | The default for a new install. The game's own texture filtering, no FXAA. Needs 4 CPU cores and about 1.1 GB of graphics memory |
| Balanced 40 | 1x | Off | Bilinear | 40 | As Low-spec 60 at a third of the CPU work of 120. Paces evenly on 120 Hz and 40 Hz displays. Recommended below 4 CPU cores |
| Performance 120 | 1x | Off | FSR 1 | 120 | The default on a discrete GPU with 6 GB or more, 6 or more CPU threads and a 120 Hz display |
| Quality 60 | 2x | 4x | Bilinear | 60 | |

On the M4 Pro Mac mini, the current free-roam qualification averages about
60 fps at 1x, but 40 fps with QUALITY 60. Start with LOW-SPEC 60 and raise
scale or MSAA separately; [the measured matrix](platforms.md#macos-on-apple-silicon) gives
the limits of that test.

Where the sun's shadows are off (**SHADOWS > OFF BY DAY**, Ultra Low 30, and the Android presets that turn them off), the game still draws them from 18:50 to 08:02 game time: the same passes light the road in front of the headlights.

1x is the console's 1280 × 720; up to 4x is available. Output scaling is bilinear, CAS or FSR 1, plus FSR 2 and FSR 3 (they use the game's depth, motion and a jittered scene; [Renderer](renderer.md)), and NVIDIA DLSS on Windows with an RTX GPU. Setup provides them all: it downloads AMD's FidelityFX runtime and NVIDIA's DLSS runtime on Windows into `upscalers/` beside the game, and builds the FidelityFX library on Linux, macOS and Android. A newer `nvngx_dlss.dll` in its own `upscalers/dlss/<version>/` folder is used first. An upscaler that is set but cannot run (DLSS without an RTX GPU, or on Linux and macOS) shows "(UNAVAILABLE)" and the game uses FSR 1, as the resolution line under the settings says. **SHARPENING** sets how much FSR sharpens. Ultrawide displays get a wider field of view with the HUD kept at 16:9. Bloom, motion blur and depth of field are optional. **TEXTURE GAMMA > FAST** makes terrain and foliage a little darker and saves about 8 % of the GPU's frame on a Mac; it makes no difference on a desktop GPU. On Linux, **SCENE SHADING > COARSE** shades the scene once per 2 × 2 pixels: a little softer, and about 8 % of the GPU's frame saved on a Steam Deck.

**POST-PROCESS AA** (FXAA) smooths the game world only, so HUD text stays sharp; **AA ON THE HUD** smooths everything, as before. **ANISOTROPIC FILTERING** and **TEXTURE DETAIL** apply to the world's textures. **TEXTURE SIZE** (1024, 512 or 256) loads large textures from a smaller level for graphics cards with little memory: the world is softer up close. It applies at the next start; the sun's shadows and the HUD keep the game's own filtering. **COLOUR LUT** gives the world a different look from a `.cube` colour table (17 or 33 points, as photo and video editors export) put in a `luts` folder you create in the state folder (`%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview\luts`); **LUT STRENGTH** blends it with the game's colours. The HUD keeps its colours, though translucent HUD panels show the game's colours behind them. These apply at once on the Vulkan renderer.

## Frame generation with Lossless Scaling

The game has no built-in frame generation yet ([planned](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/UPSCALING_BACKLOG.md)). If you own [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/), you can run it over the game window on Windows:

1. Play in a window or in fullscreen (<kbd>F11</kbd>). Both are borderless windows, which Lossless Scaling can capture.
2. In **F6 > DISPLAY**, set **GAME FRAME RATE LIMIT** to half your display's refresh rate, for example 60 on a 120 Hz display.
3. In Lossless Scaling, set **Frame Generation** to LSFG 3 with a 2x multiplier, set **Scaling Type** to Off (the game already scales to your screen), then switch to the game and press the scale hotkey (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>S</kbd> by default).

The generated frames include the HUD, so its text can smear when the camera moves fast. On an RTX 4080 with a 4K display, LSFG 3 kept about 16 % of the GPU's 3D engine busy with the game at 1x and 60 fps. On Linux and the Steam Deck, the community [lsfg-vk](https://lsfg-vk.dev) Vulkan layer does the same with the `Lossless.dll` from your own Lossless Scaling install. On a Steam Deck with the game limited to 30 fps it doubled the frames sent to the screen to 60 a second, and the GPU went from 14 % to about 65 % busy at the title screen.

## HUD

**F6 > DISPLAY > HUD** shows or hides the HUD (the same as <kbd>F2</kbd>), and sets **HUD SCALE** (80 to 120 %) and **SAFE ZONE**, a margin of up to 10 % on each side for TVs that crop the picture. Both scale the HUD around the centre of the screen while you drive; the map, the pause menu and other menus keep their size. Labels that follow the world, such as event banners and driver names, move with the HUD.

## HDR

On an HDR display, turn on HDR in the system first (on Windows, **Settings > Display > Use HDR**), then **F6 > DISPLAY > HDR**. On Windows, **F6 > DISPLAY > WINDOWS HDR** does both for you: it turns on the game's HDR and switches the game's display to HDR while the game runs, then back to SDR when the game closes. A display that was already in HDR stays in HDR. If the game crashes or is ended from Task Manager while it has HDR on, the next launch switches that display back. **HDR PAPER WHITE** sets the brightness of white menus and the HUD, **HDR HIGHLIGHTS** how far bright highlights reach, and **HDR CALIBRATION** provides paper-white and peak test patterns; HIGHLIGHTS controls how strongly scene highlights expand toward that peak. **HDR COMPARE** shows SDR and HDR side by side. Every HDR setting applies at once. HDR is tested on Windows and on Android (AYN Odin 2 Portal); on Linux and macOS it's offered when the driver provides an HDR output. On Android, keep brightness and the display mode fixed while calibrating. The Odin 2 Portal advertises about 420 nits; that is not a measurement of the current output. A tone-mapped path can keep the peak square visible at every setting: in that case keep the existing peak pending measurement. Astra calibration is still unqualified; see [Android HDR calibration](android.md#hdr-calibration). HDR COMPARE pauses while calibration patterns are shown and resumes afterwards.

## Camera editor

**F6 > DISPLAY > CAMERA EDITOR** adjusts both chase views while playing.
Height and distance are offsets in metres from the current car's camera
data. Field of view and stiffness are percentages; higher stiffness makes
the yaw and height springs react faster. DEFAULT keeps the loaded camera
values; RESET CAMERA EDITOR restores them and the normal driving view.
The separate FIELD OF VIEW row continues to affect all cameras.
DRIVING VIEW also offers the game's WHEEL and car-relative REPLAY cameras;
NORMAL returns to your previous player view. These controls are qualified
on the Windows disc and v4 builds with pinned saves; see the
[camera editor notes](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md#camera-editor).

## Immersive camera

**F6 > DISPLAY > IMMERSIVE CAMERA** makes the camera react to the car: it is pushed back under acceleration and thrown forward under braking, jolts when the throttle or brake goes on, leans into corners, shakes a little at speed and under hard braking, and moves with slow breathing and head sway in the cockpit. The cockpit view gets the full effect, the hood view a little less, and the chase and bumper views only the G-forces. Choose OFF, SUBTLE, DEFAULT or STRONG, or set G-force, lean, speed shake and head motion on their own rows (CUSTOM). Changes apply at once and keep your own save. Disc and v4 use separate camera-data merges, qualified on Windows with pinned saves. On Android it comes with the mods the PC shares over Wi-Fi (not yet tried in a race there).

## Sound mix

**F6 > AUDIO** sets the level of each part of the game's sound against its own mix: **ENGINE** (your car), **OTHER CARS**, **TYRES**, **WIND**, **AMBIENCE** (crowds, traffic and the world) and **GAME MUSIC** (the radio), from 0 to 200 %. FH1's engines are quiet against the rest; raising ENGINE or lowering AMBIENCE brings them forward. **FULL DYNAMIC RANGE** turns off the game's output compressor, so loud moments keep their peaks; leave it off for TV speakers. These settings apply when the game next starts. At 100 % and with FULL DYNAMIC RANGE off the game plays its own mix unchanged. A mod that changes the same audio files is the one the settings apply to.

## Your music

**F6 > AUDIO > YOUR MUSIC** plays your own MP3 and WAV files instead of the game's radio once you are in the festival, as a soundtrack from the Xbox 360 dashboard did: the game silences its radio by itself and keeps its effects. The title screen keeps the game's own music. Put the files in the `music` folder of the install's state folder (`%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview\music`, created when you turn it on), in subfolders if you like; they play in name order or shuffled. The AUDIO page also has MUSIC VOLUME, SHUFFLE, NEXT TRACK and PREVIOUS TRACK and shows what is playing; <kbd>F9</kbd> and <kbd>Shift</kbd>+<kbd>F9</kbd> skip forward and back. On macOS and ARM builds only WAV files play for now.

## Custom radio stations

The launcher's **Radio** button turns your music into radio stations. Each one takes the place of Horizon Bass Arena, Pulse or Rocks, so you can have up to three. Give a station a name, add music folders or songs (any format FFmpeg reads), and optionally a PNG logo, which is fitted into 210 by 100 pixels for the station popup. **Keep the station's own songs too** adds your music to the station's playlist instead of replacing it. **Build stations** encodes the music and turns the stations on from the next start; the name shows in the game's radio options and loading tips in every language. Building needs [FFmpeg](https://ffmpeg.org/download.html) (on Windows, `winget install Gyan.FFmpeg`); **Locate FFmpeg** points the launcher at it. The stations copy the game's 680 MB radio bank, so they need that much disk space, and your music files are never changed. Deleting a station brings the original back after the next build. Android gets the stations the PC built through the Wi-Fi share.

## Language

The game runs in any of the disc's 18 languages. Press <kbd>F6</kbd>, open **Profile > Language** and choose a language and region with Left and Right, then restart the game.

## Controllers

Connect the controller before starting the game. XInput controllers work as they are; DirectInput devices use SDL's mappings. If one isn't recognized, or its buttons are in the wrong places, open **F6 > CONTROLS > MAP CONTROLLER**, choose it, then **MAP BUTTONS** and press each control it asks for; a control the controller lacks is skipped after a few seconds. Then try the controller: hold **Start** to save the mapping or **Back** to start over. It is kept in `config/controller_mappings.txt`, and **RESET TO DEFAULT MAPPING** removes it. If a controller doesn't show up at all, close Steam or other remapping software, reconnect it and relaunch.

### Racing wheels

A wheel drives through the same controller path: steering on the left stick, throttle on the right trigger and brake on the left trigger. Wheels that SDL knows are detected; for another, open **F6 > CONTROLS > MAP CONTROLLER**, map it, and set **RACING WHEEL** to **YES** on its page. **F6 > CONTROLS > RACING WHEEL** then shapes its input, since the game expects a thumbstick: **STEERING SATURATION** (full lock at that share of the wheel's rotation, so 50% on a 900-degree wheel locks at 225 degrees each way), **STEERING DEADZONE** (skips the game's stick deadzone), **STEERING CURVE** and **PEDAL DEADZONE**. Gamepads are not affected. Force feedback isn't supported yet, and the shaping has been tested with simulated input, not yet on a physical wheel.

### DualSense

A Sony DualSense or DualSense Edge is driven directly through SDL's PlayStation 5 driver, so it can do things the Xbox 360 game never asked for. **F6 > CONTROLS > DUALSENSE** appears once a PlayStation controller is connected. Everything there is off until you turn it on, and applies at once:

- **ADAPTIVE TRIGGERS**: **BRAKE** gives the brake trigger a resistance that rises through its travel, a pulsing band while the car's ABS releases a wheel, and a buzz when a wheel locks. **FULL** also gives the throttle a light spring with a faint, steady buzz while the driven wheels spin. **GEAR CLICK** adds a short click on the throttle at each gear change. The effects come from the car's own physics (engine, gear, ABS and wheel slip, read from the game each frame). The triggers go slack in menus, on the pause map, in the F6 menu, when the game window loses focus, and when the game quits or crashes. **TRIGGER STRENGTH** scales all of it.
- **LIGHTBAR**: **PLAYER** keeps the colour of the controller's number, **RPM** runs from green through yellow to red as the engine nears its redline and flashes at the limiter, **OFF** turns it off. **PLAYER LIGHTS** turns the player number lights under the touchpad on or off.
- **TILT STEERING** adds the controller's tilt to the left stick, held like a wheel; **TILT SENSITIVITY** 100% reaches full lock at 45 degrees. Press the touchpad to make the current tilt the centre. It also works with a DualShock 4 or a Switch Pro Controller.

The settings menu and the mapping assistant show PlayStation button marks while a PlayStation controller is the one in your hands. The game's own on-screen prompts keep the Xbox buttons.

If Steam starts the game with Steam Input on, Steam hands the game a virtual Xbox controller instead, and none of this reaches the pad; the page then says **STEAM INPUT HAS THE CONTROLLER**. Turn Steam Input off for the game (**Properties > Controller > Disable Steam Input**) and restart. On Android only a controller on USB-C gets these features; over Bluetooth Android passes buttons and rumble only.

Tested controllers:

| Controller | System | Connection | Triggers | Lightbar | Tilt | Release on quit, focus loss, crash |
| --- | --- | --- | --- | --- | --- | --- |
| DualSense | Windows 11 | USB | Yes | Yes | Yes | Yes |
| DualSense | Windows 11 | Bluetooth | Not tested | Not tested | Not tested | Not tested |

Linux, the Steam Deck, macOS, Android and the DualSense Edge have not been tried yet.

## Gameplay switches

**F6 > GAMEPLAY** turns on four switches the game kept from its development builds. All are off by default and apply at once. **SKIP VOICE-OVERS WITH A** lets A close a dialog before its voice-over ends. **AUTOMATIC CAR RESET** off stops the game from putting the car back on the road when it strays too far. **REPLAY INTRO WHEN IDLE** off keeps the title screen from replaying the intro movie after about a minute without input. **PHOTO CAMERA THROUGH WALLS** lets the photo mode camera pass through walls and terrain, at once. For a higher, farther and more zoomed photo camera, turn on the **photo_mode_limits** mod on **F6 > MODS** (it keeps your save): the camera climbs to 30 m instead of 2 m, roams three times as far from the car and zooms further. **SKIP INTRO MOVIES** on ends the splash movies at boot and goes straight to Press Start; it applies at the next start. **START IN SINGLE PLAYER** on presses through Press Start and SINGLE PLAYER for you, so the game loads straight into your career; with both on, boot goes from the launcher to free roam without a button. It only acts when a save exists (a first start still shows the menus) and stops if a screen doesn't follow as expected, leaving the menus to you. It applies at the next start. The HUD is hidden with <kbd>F2</kbd>.

### AI opponents

**F6 > GAMEPLAY > AI OPPONENTS** chooses how the other drivers race. It applies from the next event.

- **STOCK**: the game as shipped.
- **NO RUBBER-BANDING**: an AI driver that gets ahead of you no longer slows down to wait, and one that falls behind no longer drives better to catch up. It also stops the game from adjusting the AI's skill after each race according to your times.
- **HARD**: no rubber-banding, and every opponent difficulty races one level up. At the hardest difficulty every opponent gets the game's strongest skill and most aggressive passing.

The setting changes how the AI drives, not the game's files, so it plays your own profile. Two smaller boosts are kept by every choice: by our reading of the code, cars at the back of the grid get extra power for the first few hundred metres, and your rival can get extra power and skill. Neither has been measured yet.

## Traffic and showcase cars

Turn on **F6 > MODS > HIDDEN_CARS** and restart to list the intro Corrado and showcase Mini Cooper S, 500 Abarth and Peugeot 205 T16 in the Autoshow. The traffic cars previously listed by this mod, including the tour bus, are excluded because they lack qualified player models. It plays a separate profile, so your own save is not changed. Existing traffic-car purchases remain there. If one blocks your garage, close the game and follow the [backed-up selection recovery](modding.md#enabling); it requests a starter Corrado without deleting the purchased car.

The four variants were bought, saved, reloaded and driven on the base Windows build. Full garage and paint-shop checks, and v4 qualification, are still pending; see the [audit and test limits](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/HIDDEN_CARS.md).

## Saves

Saves are in the install's state folder, `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview\user` (under `data` for a portable install).

Post-race gameplay replays cannot yet be saved and reopened after quitting,
or exported to video. F8 saves a single PNG. The replay persistence work and
its verification gates are described in the
[gameplay replay research](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/GAMEPLAY_REPLAYS.md).

- **Backups.** After each save, the save files are copied to `backups\saves`. The last 10 are kept. Restore one from **SETTINGS > PROFILE > SAVE BACKUPS**.
- **Photos.** <kbd>F8</kbd> writes PNGs to the `photos` folder in the state folder. Press <kbd>F2</kbd> first for a photo without the HUD.
- **A save from another install.** On Linux and macOS, the launcher's **Import a save** takes another Pinyon Shift install folder or a ZIP of one; the current save is backed up first, and a save from the cheats or mods tree stays in that tree. From a terminal on any system: `python3 tools/pinyon.py import-save <folder-or-zip>`.
- **Saves from Xenia.** A Xenia save is signed with its profile's XUID, so copying it over doesn't work. On Linux and macOS, **Import a save** has a Xenia option; on any system, `python3 tools/pinyon.py import-save --xenia <folder>` does it, or on Windows the tool from a repository checkout:

```powershell
.\tools\import-xenia-save.ps1 -StateRoot .local\preview -Source 'C:\Xenia\content\E030000012345678\4D5309C9'
```

The previous Pinyon Shift save is kept; `-Restore` switches back to it.

A save from Xenia running title update v4 needs the [v4 build](dlc.md#title-update-v4): the base build can't load it, and the game would ask for an update from Xbox Live. The import says so, and so does **Play** while the base build is chosen.

## Trainer

Turn cheats on in **SETTINGS > CHEATS** and restart. The game then plays a separate copy of your profile (`user-modded` in the state folder), so cheated progress never reaches your own save. <kbd>F10</kbd> opens the trainer:

- **PLAYER**: set or add credits, set the wristband level.
- **WORLD**: game speed, time of day, **DAY LENGTH** (how many real minutes 24 game hours take, from 12 minutes to 24 hours, or this PC's clock; events that set their own time still do), free camera, collectibles on the map, and **ANY CAR IN ANY EVENT**. With it on, events drop their class, make, year and other car limits, so the car you drive is eligible as it is. Turn it on before you drive up to the event.
- **GRAPHICS** and **DEBUG**: bloom, motion blur, depth of field, filtering, a file-open log.

**VEHICLE** has an experimental **FAST TRAVEL ANYWHERE** option, off by default.
Open the game's map, choose a road and press <kbd>X</kbd> to use the game's
normal travel confirmation, loading screen and streaming wait. A marker the
game can already travel to, such as an outpost or the festival, keeps its
normal arrival spot; any other marker takes you to its nearest road. Races and
scripted travel locks still apply. This temporary trainer option is separate
from v4's Fast Travel Anywhere ownership setting.

After selecting a road on the map, **GPS TO LAST MAP ROAD** requests guidance
there. **SAVE LAST MAP ROAD** remembers that road in the settings file;
**GPS TO SAVED ROAD** reuses it after a restart. Advanced users can request a
custom target once with `cheat_gps_destination = "x,y,z"` (world metres).
Launch requests wait for the first free roam; requests during races are rejected.
The title's destination lock still applies. A saved
point also has a separate **TELEPORT TO SAVED ROAD** action. Open the game's
full map (A from the pause menu's MAP page) before opening the trainer for a teleport; the request expires after ten
seconds if the map cannot accept it. Confirm the title's travel dialog with A.
Explicit trainer travel
snaps to a road, uses the title's heading and charges no credits. Centre the
map on a collectible's marker to travel to a road nearby. Advanced users can request it once
with `cheat_teleport_destination = "x,y,z"`. Twenty consecutive landings and custom route guidance were tested on Windows
with both the base game and v4. Other platforms are not qualified; details are in [the research notes](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/research/TRAVEL_DESTINATIONS.md).

## Telemetry out

**F6 > GAMEPLAY > TELEMETRY OUT (UDP)** sends the player car's telemetry over UDP in Forza Motorsport 7's Data Out "Dash" layout (311 bytes), which SimHub, dashboards and motion software read. It goes to `127.0.0.1:5300` unless `telemetry_udp_target = "host:port"` in `pinyon_shift.toml` says otherwise; point the tool at that port and choose its Forza Motorsport 7 profile. Each frame carries whether you're driving, engine RPM, idle and redline, speed, gear (reverse 0, neutral 11), throttle, brake, clutch, handbrake and steering (as the car receives them, after assists), and for each wheel its rotation speed, slip ratio, slip angle and combined slip (1 is peak grip), suspension travel in metres and normalised, and a surface rumble. Normalised travel is scaled to the range the car has shown since it spawned, since the game's travel limits are not traced. Surface rumble is the game's own low-frequency rumble motor (bumps, kerbs and impacts, 0 to 1, the same for every wheel; base game only), which bass shakers can play as road feel. The forward velocity carries the speed too, for tools that read it there. Menus and the pause screen send race off, as the game's own Data Out does, so shakers fall silent: the gameplay view is the first check, and a stopped simulation (engine, wheels and suspension holding exactly still for half a second) the second. `telemetry_udp_moving_only = true` also sends race off while the car stands still. `telemetry_udp_format = "horizon"` sends the Forza Horizon 4/5 layout instead (324 bytes) for a tool set to that game. Position, the other motion and lap fields are sent as 0 until the game's values for them are traced. **telemetry_probe = true** records candidate fields to `telemetry-probe-<time>.csv` beside the runtime log, for tracing the rest.

## Treasure Map

The Treasure Map add-on was sold through a service that no longer exists. It's included and on by default. Turn it off with **F6 > GAMEPLAY > TREASURE MAP** or in the launcher's **Settings**. Once a save's map is revealed it stays revealed.
