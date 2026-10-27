---
title: DLC and title update
section: Playing
order: 3
description: Import your own Forza Horizon DLC packages and build the optional title update v4 version.
---

# DLC and title update

DLC comes from your own Xbox 360 packages or the community downloads below. The launcher (on Windows, Linux and macOS) verifies each one against a pinned catalog of 21 official *Forza Horizon* packages plus UDLC v1.2 and its Traffic Car Unlocker, then imports it. Ordinary imports start disabled, and each package is enabled separately. Close the game before changing DLC.

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

- The original package files: no file extension, beginning with `LIVE`, `CON` or `PIRS`. A folder or ZIP holding them works too, however deeply the packages are nested: subfolders are searched, as are folders inside a ZIP and ZIPs inside a ZIP. Choose several files or folders at once (in the launcher's file picker, or by dropping them on the DLC panel on Linux and macOS) or pass several paths to `pinyon.py dlc import`; they import as one batch. ZIPs that can't be read (Deflate64, which Windows uses for large ZIPs, or encrypted ones) are skipped and named; extract them first.
- Packages are listed by the name in their header, not by the file's name. A file shared as "2006 Ford GTX1" is the December IGN Car Pack and shows under that name. After importing, enable the package; its cars are bought in the Autoshow.
- A package outside the verified catalog is refused with its header name and the reason. Content types other than Marketplace DLC, such as an offer or licence package, hold no cars to import.
- Horizon Rally: one widely shared copy of the standalone Rally Expansion Pack is damaged (three dirt-track terrain files are corrupt) and is refused with that reason. Use another copy of the package, such as the one in the full DLC set.
- DLC already installed in Xenia: choose Xenia's content folder for the game, `4D5309C9`, which holds `00000002` and `Headers` (on Windows usually `Documents\Xenia\content\<profile>\4D5309C9`, or `content\0000000000000000\4D5309C9` in older builds). Each unpacked package is verified by its files and by the licence in its header; Xenia's copy isn't changed. A package folder without its `Headers` entry can't be verified: import the original package instead.

## Community UDLC

[UDLC v1.2](https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/udlcv12)
by Warshack4874 adds cars from the Xbox 360 versions of *Forza Horizon 2*
and its *Fast & Furious* edition. The optional
[Traffic Car Unlocker](https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/udlc-traffic-car-unlocker)
(2026-01-13 release) adds traffic cars and requires UDLC. These are community
packages, identified as community content in import records. Pinyon Shift does not
redistribute them or download them automatically: download the ZIPs in your
own browser from ModDB.

In the launcher's **DLC** panel, find **UDLC Pack** and choose
**Download from ModDB**. Download `UDLCv1.2.zip` on the page that opens in
your browser (about 1 GB); the launcher waits up to four hours and installs
it when it finishes in Downloads. Tick **Also install the Traffic Car
Unlocker** before clicking to open its page and install both packages.
If you already have the ZIPs, choose **Install UDLC** and select the UDLC
ZIP and, optionally, the unlocker ZIP together. Both actions enable the
imported packages, which are marked **Community** in the list.

From a terminal, leave the ZIPs in Downloads and run:

```text
python tools/pinyon.py dlc udlc --find
python tools/pinyon.py dlc udlc --find --traffic
```

To open the pages and wait for your browser to finish downloading, add
`--open-pages --wait 14400`. You can also give the downloaded ZIP paths
directly. Add `--state-root DIR` to choose an installation's state folder.
The command checks each ZIP's size and MD5, verifies the inner packages and
extracted files against pinned SHA-256 values, imports them and enables
UDLC and the imported unlocker. A first import with `dlc import` leaves them disabled.
Turning UDLC off also turns its unlocker off; the unlocker cannot be enabled
without UDLC. The launcher asks for confirmation first: owned UDLC cars
are hidden while it is off, the game picks another car, and the UDLC cars
return when it is turned on again. The save file is not changed.
The older v1.11 ZIP is refused with a link to v1.2.

On Windows with an RTX 4080 and Vulkan, the **2002 Acura RSX Type-S** was
bought and driven on both the base and v4 builds. A fresh base launch
reloaded the purchased car and drove it. Both builds showed its name in
English and Mexican Spanish UI (the proper model name stays RSX Type-S).
These scripted checks used private saves,
test credits and an enlarged Autoshow trigger to reach the ordinary menu;
they do not qualify every car or upgrade. Import and dependency handling
were checked with the real v1.2 and Traffic ZIPs. With XE 1.01 enabled
alongside both packages, the base build reached the Autoshow and displayed
the RSX name. This does not qualify all combined content; see the
[DLC backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DLC_BACKLOG.md#community-udlc-595).

With the stock RSX selected, turning UDLC off on the tested base save
loaded a fallback Corrado and preserved the owned garage. After turning
UDLC on again, select the RSX in **Change Car**; it remained owned and
could be selected without buying it again. Other cars and purchased UDLC
upgrades have not been checked for safe removal. Keep a save backup.

On Android, import and enable on the PC first, then copy the DLC group from
the launcher's content share. It includes community and official packages
through the same path. DLC is not embedded in the APK, and the USB
`android push-data` command copies only the disc files; manual DLC transfer
also needs the state folder's `user` content and `dlc` records. UDLC gameplay
has not been tested on a phone.

The pack has a paint-shop hang with the **2015 Dodge Charger F&F** and
**2014 Maserati Ghibli F&F**, also reported on Xbox 360 hardware and Xenia.
On v4, both purchased cars stayed on **Please wait** after entering Design
Creator throughout an extended scripted check; the RSX control reached
Paint Car and responded to body/mirror selection. Avoid painting the two
F&F cars. No runtime workaround is applied for this known upstream issue.

## Title update v4

The base disc build is the default. The optional v4 build applies title update v4 to the USA disc and runs the original Rally and 1000 Club code. It's built from your disc and your own copy of the update, which is verified page by page before it's installed.

- Windows, Linux and macOS: in the launcher's DLC panel, **Import update**, then **Use v4**. **Play** builds the v4 version the first time (about as long as the first build) and starts it; **1000 Club offline** turns on the offline challenges. From a terminal: `python3 tools/pinyon.py title-update import <zip>`, `title-update enable` and `launch`.
- Linux: on a Steam Deck the v4 build runs the offline 1000 Club and reaches the Horizon Rally stage intro. macOS: the v4 build runs the 1000 Club challenges and reaches the Horizon Rally entry on an M4 Pro.
- Android: **Build APK** builds the v4 app when v4 is on; `python tools/pinyon.py android build --title-update-v4` from a terminal.

> A save written by the v4 build can't be loaded by the base build afterwards. The launcher backs up the save before the first v4 start.

The v4 build is still under qualification. Details are in the [title update v4 backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/TITLE_UPDATE_V4_BACKLOG.md) and the [DLC backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DLC_BACKLOG.md).
