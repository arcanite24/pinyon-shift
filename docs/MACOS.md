# macOS

Pinyon Shift builds and runs natively on Apple silicon Macs. The game's
Vulkan renderer runs on Metal through MoltenVK, which the build includes. As
on Windows and Linux, you choose your own disc image, and the launcher
verifies it, builds the game on your Mac and starts it.

## Requirements

- An Apple silicon Mac (M1 or newer) with macOS 13 Ventura or newer. Intel
  Macs are not supported.
- Your ISO of the USA retail disc (`MS-2505`).
- About 20 GB free.
- Apple's Command Line Tools, which provide the compiler. The launcher
  offers to install them if they are missing; nothing else needs installing.

## Install and play

1. Download `PinyonShift-Launcher-macos-arm64.zip` from the
   [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest),
   verify the SHA-256 listed there and open it. Move **Pinyon Shift** to
   **Applications** if you like.
2. The app is not notarized by Apple, so the first start needs your
   approval. Open it once, then go to **System Settings → Privacy & Security**
   and choose **Open Anyway** next to the message about Pinyon Shift. On macOS
   13 and 14 you can instead Control-click the app and choose **Open**.
3. If the launcher asks for the Command Line Tools, choose **Install the
   tools** and follow Apple's dialog, then **Check again**.
4. Choose **Choose disc image** and select your ISO, or drop it onto the
   launcher. Confirm ownership and choose **Verify and build**. The Mac stays
   awake until the build is done: about 20 minutes on an M4 Pro.
5. Choose **Play**. Press **F6** in game for settings.

On an M4 Pro, free roam runs at a median of about 105 fps at the default 1x
resolution.

## From a terminal

The launcher runs these commands. In the install's source folder or a
repository checkout:

```bash
python3 tools/pinyon.py setup --iso ~/Downloads/forza-horizon.iso
python3 tools/pinyon.py launch
```

The `python3` that comes with the Command Line Tools is enough: `setup`
downloads a pinned Python for itself, and pinned CMake and Ninja, each
checked by SHA-256, into `.local/toolchain`.

## Where things live

```text
~/Library/Application Support/PinyonShift/source/<version>/   source, tools, game files, build
  .local/preview/user/                                       saves
  .local/preview/                                            settings, game logs, crash reports
  .local/logs/                                               setup logs
```

`PINYON_SHIFT_INSTALL_ROOT` moves the install elsewhere, for example to an
external drive.

## Troubleshooting

- **"Pinyon Shift" cannot be opened.** Approve it under Privacy & Security,
  step 2 above.
- **Setup failed.** The launcher names the step and the log. The same report
  is in `.local/logs/setup-error.json`; attach it when you file an issue.
- **The build cannot find a compiler.** Run `xcode-select --install` in
  Terminal, or reinstall the Command Line Tools from Apple's developer site.

## Uninstalling

Copy your saves out of `.local/preview/user` if you want to keep them, then
delete the app and `~/Library/Application Support/PinyonShift`.

## Status

| System | Status |
| --- | --- |
| Mac mini, M4 Pro, macOS 26 | Release app to a built game in 18 minutes, installed on an external drive; free roam route passes |
| Other Apple silicon Macs | Not tested yet |

DLC import, the title update build and crash bundles are not available on
macOS yet.
