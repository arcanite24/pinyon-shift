# Save sync through folder-sync apps

Status: ported from Lavender Shift on 2026-11-15 for Windows (game and
launcher) and Android (the game's folder argument). Code:
`src/save_sync.{h,cpp}`, the PROFILE > SAVE SYNC page in
`src/ui/settings_menu.cpp`, `launcher/PinyonShift.Launcher/MainWindow.Sync.cs`
and `SaveSyncStatus.cs`, and `syncFolder()` in `PinyonShiftActivity.java`.
Test: `tests/save/save_sync_test.cpp` (below).

**Goal.** A player who already runs a folder-sync app (Syncthing,
Syncthing-Fork on Android, Dropbox, OneDrive, Google Drive for desktop,
Nextcloud, a NAS share, or a USB stick) points Pinyon Shift at a folder that
app syncs. The save and achievements then follow them between the PC, the
Steam Deck and an Android device. There's no manual copying, no server of
ours, and no way for the sync app to corrupt a save.

**Non-goals.** Our own cloud service or account. Live sync while two devices
play at once. Syncing caches, shaders, logs, DLC, mods or graphics settings.

## Decisions

1. **Syncthing is the main target**, but nothing depends on it. The design
   only needs a folder that eventually looks the same on every device. The
   Android default folder was chosen so that Syncthing-Fork can reach it.
2. **The "which save" choice is made in the game only**, on PROFILE > SAVE
   SYNC, so every platform shares one implementation. The launcher shows a
   status line and doesn't decide anything.
3. **`marketplace\tmpfile` stays in the save**, as in Lavender: we can't show
   that the title recreates it. The archive is a *stored* (uncompressed) ZIP,
   so a file that keeps its size keeps its offset, and Syncthing (which sends
   only changed 128 KiB blocks) transfers just what the title rewrote. The
   reference save's profile folder is 23 MB.
4. **Lineage decides, clocks never do.** Timestamps are shown to the player
   and nothing more.
5. **A v4 save is one-way.** The base game can't load a save the v4 title
   update has written. Each manifest says which build published it
   (`version = "base"` or `"v4"`). A base build lists a v4 device's save as
   *needs the v4 build* and never loads it, on its own or by choice. A v4
   build loads either.
6. **Only the player's own save syncs**: `<state>\user`. The XE mod's and the
   modded profiles (`user-modded`) don't. A scripted route
   (`PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT` set) never syncs, because
   `tools/create-render-seed.py` copies the settings, and the folder with them,
   into the seed.

## Why syncing `user\` as it is doesn't work

- `user\` mixes the save with things that must not travel. That includes
  `0000000000000000\` (3 GB of installed DLC on the reference save). The
  settings and caches sit next to it in the state folder.
- The save is several files that must agree with each other (`ForzaProfile`,
  `PlayerDatabase`, `GameplayLog`, `rally-progress.toml`, the content headers).
  A file-by-file sync can deliver a new `PlayerDatabase` next to an old
  `ForzaProfile`, and when both devices played, sync apps resolve the
  conflict file by file.
- The title writes those files in place while it runs.
- On Android the save is in `Android/data/<package>`, which no other app can
  open on Android 11 and later.

## How it works

The live save stays where it is. Each device writes **only its own files** in
`<sync folder>\devices\`, so a sync app never sees two writers of one file:

```
<sync folder>\devices\
  <device-id>.lsave              stored ZIP of the profile folders (not 0000000000000000)
  <device-id>.achievements.toml  copy of user\achievements\4D5309C9.toml
  <device-id>.toml               manifest, written last
```

Manifest (flat TOML, the same `name = value` rules as the settings file):

```toml
format = 1
device_id = "8c1e…"          # 32 hex digits, random, made once per device
device_name = "MULTIVAC"     # the computer's name, Build.MODEL on Android, or --pinyon_shift_device_name
platform = "windows"
version = "v4"               # the build that published it: "base" or "v4"
written_utc = "2026-11-15T18:02:11Z"
save_hash = "…"              # SHA-256 over the sorted save file names, sizes and contents
based_on = "…"               # the newest entry of history
history = "h1,h2,…"          # up to 64 earlier or replaced save hashes, newest first
archive_sha256 = "…"
archive_bytes = 23068672
achievements = 23
```

A device's state lives in `<state>\config\save_sync.toml`: its id, the
machine name the id belongs to, `current` (the hash of the save it has),
`history`, the last export, and a pending import. If the machine name changes
(a copied or cloned state folder), the device gets a new id, so two installs
never write the same files.

**Reading a remote.** A remote is any `<32 hex>.toml` other than this
device's. Its archive must have the size and SHA-256 the manifest gives, which
covers a manifest that arrives before its archive, or a partial download.
Sync-app conflict copies (`*.sync-conflict-*`, `(conflicted copy)`) are never
read, because their names aren't device ids. A manifest with a newer `format`
is skipped with a log line. A manifest without `version` counts as `base`.

**Relation** of a remote R to this device:

| Relation | Condition |
|---|---|
| Same | `R.save_hash == current` |
| Local ahead | R's hash is in this device's history |
| Remote ahead | this device has no save, or `current` is in R's history |
| Diverged | neither |

### At start (`OnConfigurePaths`, before the title or the achievements load)

1. Hash the live save. If it differs from `current`, that's progress made
   since the last export (a crash, or sync was off), so the save advances (the
   old hash goes into history).
2. Merge every remote's achievement unlocks into this device's (the union,
   keeping the earliest time).
3. If the player chose a save on SAVE SYNC, import it. Otherwise, if exactly
   one newest remote this build can load is *remote ahead*, import it without
   asking.
4. **Import** stages a copy of this device's user folder with its profile
   folders replaced by the archive's, so the installed DLC's headers and the
   achievements stay. It checks the staged save's hash, adds it as a backup
   slot (`…-sync`), and puts it in place with the save backups' restore. The
   restore first backs up the current save (`…-before-restore`), so every
   import can be undone from SAVE BACKUPS. The remote's history is merged into
   this device's.
5. Publish this device's save if it changed.

### While the game runs

- **Export** runs on the save backups thread right after each snapshot, from
  the snapshot's copy and never from the live files. That's at most once per
  ten minutes, after the save has been still for five seconds, and once at
  exit. After the title stops, the game exports from the live folder once more
  (this also covers backups being off).
- **Nothing is imported mid-session.** A watcher polls the folder 15 s after
  start and then every 30 s, and shows toasts: "LOADED THE SAVE FROM X",
  "A NEWER SAVE FROM X IS WAITING" (it loads at the next start), "YOUR SAVE
  ALSO CHANGED ON X" (choose on SAVE SYNC), or "THE SYNC FOLDER IS NOT
  REACHABLE".

### Choosing (SETTINGS > PROFILE > SAVE SYNC)

Lists each other device with *same save*, *older*, *newer*, *different* or
*needs the v4 build*. A newer or different save this build can load offers:

- **Load X's save at next start**: imported at the next start, like a backup
  restore.
- **Keep this device's save**: X's save hash goes into this device's
  history, and the next export publishes it. X then sees this device as
  *remote ahead* and loads it without asking. Neither device asks again.

## Turning it on

- **PC launcher**: **Save sync** in the footer opens a menu to choose a
  folder, open it, or turn sync off. A folder inside the install or the state
  folder is refused. The launcher writes the choice to the game's
  `config\pinyon_shift.toml` as `pinyon_shift_sync_folder` (with forward
  slashes, since the value is a TOML string), so no command-line quoting is
  involved. The line under Play shows the status from the manifests
  (`SaveSyncStatus.cs`).
- **Without the launcher** (Linux, macOS, the Deck):
  `--pinyon_shift_sync_folder=<folder>` (and optionally
  `--pinyon_shift_device_name=<name>`) on the command line, or the same names
  in `config/pinyon_shift.toml`. The game reads them from the file itself,
  because sync starts before the SDK loads that file.
- **Android**: always on, in `Android/media/studio.deimos.pinyonshift/sync`
  on internal storage. Point Syncthing-Fork or BasicSync (with "All files
  access") at that folder. A `--pinyon_shift_sync_folder=` line in
  `config/android-arguments.txt` or the launch intent overrides the folder
  (the last value wins), and an empty value turns sync off.
- A missing folder (an unplugged drive) is reported, never created. Only the
  `devices` subfolder is made inside an existing folder.

## Test

```
cmake --build out/build/win-amd64-v4 --target pinyon_shift_save_sync_tests
out\build\win-amd64-v4\pinyon_shift_save_sync_tests.exe
```

The test uses two state folders and one sync folder, and covers:

- the archive round trip, and a hash that ignores caches and DLC;
- the first device's save loading on a second device that has none;
- fast-forward, with the replaced save kept as a backup;
- divergence seen from both sides;
- achievement merging;
- *keep this device's*, after which the other device loads it without asking;
- a chosen import;
- a damaged archive ignored, then loaded once it's whole;
- a sync-conflict copy ignored;
- a missing folder reported and not created.

## Not done yet

- **Checked on multivac, 2026-11-15,** with the v4 build. Two state folders
  were copied from a render seed. Device B's profile folder was deleted, and
  one sync folder had a space in its name, set through each
  `pinyon_shift.toml` as the launcher writes it:
  - A published at start (`sync.export`, version `v4`). Python's `zipfile`
    read its 23 MB archive as a valid stored ZIP of 18 save files.
  - B, at its first start, loaded A's save without asking. It backed up its
    own first (`…-before-restore`, then `…-sync`, `save.restore.applied`,
    `sync.import`) and then published it. `PlayerDatabase` matched A's
    byte for byte, and B's installed DLC folder stayed in place.

  Not yet checked: the toasts and SAVE SYNC page on screen, an export during
  play, a base build listing a v4 save, the launcher's menu on screen, and
  Android with a sync app. Lavender checked the Android side with BasicSync
  on an Odin 2 Portal, and Pinyon's activity passes the folder the same way.
- An APK built on the prebuilt shell (TP-5) takes `classes.dex` from the
  shell, which won't have the `syncFolder()` change until the next shell is
  released. A source build compiles it. The Java change hasn't been compiled
  or run on a device yet.
- Photos (an append-only export) and portable settings (cheats, frame rate).
