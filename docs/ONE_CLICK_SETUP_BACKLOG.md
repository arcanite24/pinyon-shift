# One-click setup backlog: download, import the disc, play

Status: **open**, created 2026-10-08 at `dev` `a1a7675`.

Goal: a player downloads `PinyonShift-Launcher.zip`, drops in their own disc
image and plays, on Windows and on an Android device, with nothing installed
by hand. Anything the build or the game needs is downloaded, installed or
repaired by the launcher, or checked before a long build with a clear fix.
Android needs no developer options: no USB debugging and no adb.

This backlog closes the gaps listed in
[#393](https://github.com/arcanite24/pinyon-shift/issues/393) and the
"easier Android build, USB installation and game-data transfer" roadmap item.
It also covers [#389](https://github.com/arcanite24/pinyon-shift/issues/389),
where Play repeated a long preparation step.

## Windows

| ID | Item | Status |
| --- | --- | --- |
| W-1 | Free-space check before setup, on the install drive and on the system drive (Build Tools, build temp), with one figure in `config/release-toolchain.json` used by the docs and the failure hint | Done |
| W-2 | A portable, pinned Ninja like CMake and LLVM, so neither build depends on a Visual Studio component | Done |
| W-3 | Repair an incomplete Visual Studio: when the Windows SDK probe fails, add the pinned SDK component with the installer's `modify` (one administrator prompt) and probe again (#339). The Visual Studio Installer already on the PC updates the install and adds the components in `visual_studio.repair_components`, once | Done |
| W-4 | Reboot: a Build Tools exit code 3010 or a pending reboot stops setup with a "restart required" failure; the launcher offers Restart now and resumes setup after sign-in | Setup side done: a 3010 followed by a failing environment stops with `reboot-required`; launcher button open |
| W-5 | Vulkan 1.3 driver checked before a 20 to 60 minute build, with the vendor's driver page | Open |
| W-6 | Visual C++ runtime: check the game's runtime DLLs and install Microsoft's signed redistributable when they are missing | Open |
| W-7 | Path-length limit for custom install folders as well as portable ones | Open |
| W-8 | Remove the downloaded-file mark from the extracted toolchains and payload | Open |
| W-9 | Network check of the download hosts still needed, before the first download | Done |
| W-10 | Build Tools progress: the installer's own progress window and a heartbeat in the launcher | Done |
| W-11 | #389: a Vulkan preparation that was cancelled or failed is not repeated at every Play, and Play shows "Preparing graphics", not the build step | Done |

Not planned: a Defender exclusion offer. It changes a security setting
for the player, and the existing antivirus hint names the folder to allow.

## Android

| ID | Item | Status |
| --- | --- | --- |
| A-1 | The Android build provisions everything itself (CMake and Ninja from the pinned toolchain, the JDK and SDK as now) and builds the v4 APK when v4 is chosen in the launcher | Open |
| A-2 | The APK is easy to find: an Android panel in the launcher with the APK's path, Show in folder and Save a copy | Open |
| A-3 | Install without adb: the launcher serves the APK on the local network while the panel is open, with a QR code to scan on the device | Open |
| A-4 | Game files without adb: the app opens a setup screen when the game is missing. It receives the game, the v4 update, DLC and Rally data from the launcher over the local network with a pairing code. It can also import a folder copied to the device over USB | Open |
| A-5 | adb stays for developers: Install over USB when a device with USB debugging is connected | Open |
| A-6 | Documentation: README, `docs/ANDROID.md` and the launcher's own text | Open |

### Local network transfer (A-3, A-4)

- **When it serves.** The launcher serves only while its Android panel is
  open, on the private network, and only these files: the built APK, the
  extracted game, and, if present, the installed v4 update and enabled DLC
  content. A save is sent only when the player chooses it on the device, and
  the device keeps a backup of its own first.
- **Access.** Every request but the APK download needs the six-digit pairing
  code the panel shows. The code changes each time the panel opens. The APK
  link carries its own random token. Nothing is uploaded from the device to
  the PC.
- **Discovery.** The device finds the launcher by a UDP broadcast on the
  local network, or the player types the address the panel shows.
- **Firewall.** Windows asks once to allow the launcher on private networks.
