---
title: DLC and title update
section: Playing
order: 3
description: Import your own Forza Horizon DLC packages and build the optional title update v4 version.
---

# DLC and title update

DLC comes from your own Xbox 360 packages. The launcher (on Windows, Linux and macOS) verifies each one against a pinned catalog of 21 *Forza Horizon* packages, then imports it. Imports start disabled, and each package is enabled separately. Close the game before changing DLC.

## Supported packages

| Package | State |
| --- | --- |
| Monthly car packs (October to April) | Qualified: cars appear in the Autoshow, can be bought and driven |
| VIP Membership, Honda Challenge, Pre-Order, Season Pass and single cars | Cars qualified. The Honda challenge flow isn't qualified |
| Horizon Rally | Native on the v4 build. On the base build, a prepared overlay makes the championships playable from <kbd>F6</kbd> |
| 1000 Club | Offline car challenges with saved medals on the v4 build ("1000 Club offline" in the launcher) |
| Treasure Map | Included and on by default |

Import every copy of a package you own: verified variants of the same package combine their licences. The full November pack, for example, needs its full-licence copy.

Rally championships do not include open-world Rally travel. A save-safe entry,
reload and return to Colorado remain unqualified on both builds. The
[Rally free-roam investigation](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RALLY_FREEROAM.md)
has a private initial-placement probe for developers; it is not a player option.

## What to import

- The original package files: no file extension, beginning with `LIVE`, `CON` or `PIRS`. A folder or ZIP holding them works too. ZIPs that can't be read (Deflate64, which Windows uses for large ZIPs, or encrypted ones) are skipped and named; extract them first.
- Packages are listed by the name in their header, not by the file's name. A file shared as "2006 Ford GTX1" is the December IGN Car Pack and shows under that name. After importing, enable the package; its cars are bought in the Autoshow.
- Horizon Rally: one widely shared copy of the standalone Rally Expansion Pack is damaged (three dirt-track terrain files are corrupt) and is refused with that reason. Use another copy of the package, such as the one in the full DLC set.
- DLC already installed in Xenia: choose Xenia's content folder for the game, `4D5309C9`, which holds `00000002` and `Headers` (on Windows usually `Documents\Xenia\content\<profile>\4D5309C9`, or `content\0000000000000000\4D5309C9` in older builds). Each unpacked package is verified by its files and by the licence in its header; Xenia's copy isn't changed. A package folder without its `Headers` entry can't be verified: import the original package instead.

## Title update v4

The base disc build is the default. The optional v4 build applies title update v4 to the USA disc and runs the original Rally and 1000 Club code. It's built from your disc and your own copy of the update, which is verified page by page before it's installed.

- Windows, Linux and macOS: in the launcher's DLC panel, **Import update**, then **Use v4**. **Play** builds the v4 version the first time (about as long as the first build) and starts it; **1000 Club offline** turns on the offline challenges. From a terminal: `python3 tools/pinyon.py title-update import <zip>`, `title-update enable` and `launch`.
- Linux: on a Steam Deck the v4 build runs the offline 1000 Club and reaches the Horizon Rally stage intro. macOS: the v4 build runs the 1000 Club challenges and reaches the Horizon Rally entry on an M4 Pro.
- Android: **Build APK** builds the v4 app when v4 is on; `python tools/pinyon.py android build --title-update-v4` from a terminal.

> A save written by the v4 build can't be loaded by the base build afterwards. The launcher backs up the save before the first v4 start.

The v4 build is still under qualification. Details are in the [title update v4 backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/TITLE_UPDATE_V4_BACKLOG.md) and the [DLC backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DLC_BACKLOG.md).
