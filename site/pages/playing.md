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
| <kbd>F3</kbd> | Performance panel |
| <kbd>F7</kbd> | Achievements |
| <kbd>F8</kbd> | Save the current frame as a PNG photo |
| <kbd>F10</kbd> | Trainer: credits, game speed, time of day, free camera. Needs cheats on |
| <kbd>F11</kbd> | Fullscreen |

On a controller, hold **Back + Start** together (View + Menu on a Steam Deck) to open the settings, and **LS + RS** for the performance panel; both chords can be changed in **F6 > CONTROLS > CONTROLLER**. Keys can be rebound in **F6 > CONTROLS**. In the game's own menus, <kbd>Space</kbd> or a left click acts as the A button and <kbd>Enter</kbd> as Start.

## Graphics presets

| Preset | Resolution | MSAA | Output | Rate | Notes |
| --- | --- | --- | --- | ---: | --- |
| Low-spec 60 | 1x | Off | Bilinear | 60 | The default for a new install. The game's own texture filtering, no FXAA. Needs 4 CPU cores and about 1.1 GB of graphics memory |
| Balanced 40 | 1x | Off | Bilinear | 40 | As Low-spec 60 at a third of the CPU work of 120. Paces evenly on 120 Hz and 40 Hz displays. Recommended below 4 CPU cores |
| Performance 120 | 1x | Off | FSR 1 | 120 | The default on a discrete GPU with 6 GB or more, 6 or more CPU threads and a 120 Hz display |
| Quality 60 | 2x | 4x | Bilinear | 60 | |

1x is the console's 1280 × 720; up to 4x is available. Output scaling is bilinear, CAS or FSR 1. Ultrawide displays get a wider field of view with the HUD kept at 16:9. Bloom, motion blur and depth of field are optional.

## Language

The game runs in any of the disc's 18 languages. Press <kbd>F6</kbd>, open **Profile > Language** and choose a language and region with Left and Right, then restart the game.

## Controllers

Connect the controller before starting the game. XInput controllers work as they are; DirectInput devices use SDL's mappings. If one isn't recognized, close Steam or other remapping software, reconnect it and relaunch. Racing wheels aren't supported yet.

## Saves

Saves are in the install's state folder, `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview\user` (under `data` for a portable install).

- **Backups.** After each save, the save files are copied to `backups\saves`. The last 10 are kept. Restore one from **SETTINGS > PROFILE > SAVE BACKUPS**.
- **Photos.** <kbd>F8</kbd> writes PNGs to the `photos` folder in the state folder.
- **Saves from Xenia.** A Xenia save is signed with its profile's XUID, so copying it over doesn't work. Import it with the tool from a repository checkout:

```powershell
.\tools\import-xenia-save.ps1 -StateRoot .local\preview -Source 'C:\Xenia\content\E030000012345678\4D5309C9'
```

The previous Pinyon Shift save is kept; `-Restore` switches back to it.

## Treasure Map

The Treasure Map add-on was sold through a service that no longer exists. It's included and on by default. Turn it off in the launcher's **Settings**. Once a save's map is revealed it stays revealed.
