# Building

The supported build environment is 64-bit Windows 10 or 11 with PowerShell 5.1
or newer, a GPU with Vulkan 1.3, an
internet connection, and about 30 GB of free disk space.

Setup requires Visual Studio 2022 C++ Build Tools 17.1 or newer. Before
building, the pinned compiler checks the selected C++ library for C++23
`std::byteswap` and the selected Windows SDK headers for `D3D12_OPTIONS8`.
The latter is needed to compile the retained SDK backend. An incompatible
environment stops at this check with compiler diagnostics and update
instructions. Update the C++ tools or Windows SDK through the Visual Studio
Installer, then rerun setup; the game and saves are unchanged.

Run:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso
```

The script performs six reproducible stages:

1. verifies the exact ISO size and SHA-256 against `config/supported-dumps.json`;
2. installs Visual Studio Build Tools when missing and downloads pinned portable
   tools whose hashes are recorded in `config/release-toolchain.json`;
3. initializes the pinned ShiftGlue submodule, or clones the same revision for a packaged launcher;
4. extracts the disc and generates translated source under `.local/`;
5. configures and compiles `out/build/win-amd64-release/pinyon_shift.exe`
   for supported Vulkan play; and
6. fills Vulkan shader storage in a private startup run before the first launch.
   Vulkan also translates and stores newly encountered shaders during play.

Vulkan is the sole supported graphics API. Config schema 28 migrates saved
Direct3D 12 selections to Vulkan without changing saves. Direct3D 12 remains
legacy developer code and is absent from player settings; it is not an automatic
fallback. Its retained shader tooling requires an explicit `-LegacyD3D12` switch
on `prepare-fh1-shaders.ps1`. Ordinary setup and launch never prepare those packs.

Visual Studio initialization uses `%ProgramData%\PinyonShift\build-temp`
for its child process, so parentheses in a portable install path do not
break VsDevCmd. The launcher's original TEMP/TMP directories are preserved.

The original ISO is opened read-only and is never changed. Setup can be safely
run again after a failure; completed downloads and extraction are reused after
verification. Everything produced from the disc is ignored by Git.

To verify only the image:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso -VerifyOnly
```

To start the built game, run `.\tools\launch-preview.ps1`, or
`python tools/pinyon.py launch` without PowerShell. The latter takes
`--state-root`, `--hidden` and game arguments after `--`, and is the launcher
for Linux builds.

To rebuild after changing host or ShiftGlue code:

```powershell
.\tools\build-preview.ps1
```

To build the distributable launcher package:

```powershell
.\tools\package-launcher.ps1
```

That package contains a self-contained launcher executable and a source archive.
It deliberately excludes the compiled preview, generated translations, and all
game content. An empty `portable.txt` beside the extracted launcher (or
`--portable` on its command line) makes it a portable install that keeps
everything in a `data` folder beside it; see [Portable install](INSTALLING.md#portable-install).

## Owned Rally assets

The launcher's DLC panel accepts the player's own packages, folders or ZIPs.
Imports start disabled. Enabling Rally verifies the installed payload and its
original licence, verifies the supported base-disc executables and adapter
inputs, then prepares assets under the existing state's `cache/rally_adapter`.
This uses no v4 update and does not change the source disc, package or save.

The cache names all 28 stages for the seven championships and includes authored
pace notes, seven entry activities, stage-transition flow and localized event
tables. Existing base activities and event text are preserved. Normal launch
re-verifies the enabled package, original licence, base inputs and generated
cache before mounting the entry assets. This does not qualify activity activation
or full Rally gameplay. The panel reports **Assets cached**
alongside **Gameplay unverified**. If preparation fails after enabling, the
package remains enabled and recoverable: disable and enable it again to retry,
or leave it disabled. A rebuild publishes only after preparation finishes;
previous managed cache contents are retained for recovery.

The native base-world/map check uses
`config/render-tests/fh1-rally-entry-assets.fh1test` with a private seed containing
the verified import records, prepared cache and earned Rally checkpoint.
Its normal-entry marker uses the same preflight as ordinary launch, without the
private built-in probe flag. It checks the normal profile and 28-stage loader;
it does not establish a stage start, finish or official Rally scoring.

The same operation is available from the checkout:

```powershell
.\tools\manage-dlc.ps1 -Action enable -StateRoot C:\path\to\private-state `
  -PackageId 6F6992766050D818245ADD408031E280FB5F4E634D
```

Close the game before changing DLC. See [the DLC backlog](DLC_BACKLOG.md) for
the remaining entry, gameplay and persistence gates.

## Title update v4 inputs

The base-disc build remains the default. The verified v4 package targets media
`4000D145`, version `0.0.0.12`; the supported USA disc is `2DC7007B`, version
`0.0.0.10`. The signatures differ, but all three patches still apply exactly
to this disc: every page verifies against v4's own hashes (see the
[title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md)). The v4 build is a
developer build under qualification. Do not copy this package into the base
preview: its code is recompiled from the base executable, so it ignores a
`.xexp` and must never mount v4's `media.zip`.

A developer v4 build uses separate generated code and build folders:

```powershell
. .\tools\release-common.ps1
$buildEnvironment = Enter-PinyonBuildEnvironment
# Copies of the three base executables beside the player's verified patches.
New-Item -ItemType Directory -Force .local/game/v4-codegen | Out-Null
Copy-Item .local/game/base/*.xex .local/game/v4-codegen/
Copy-Item C:\path\to\verified\update\*.xexp .local/game/v4-codegen/
& $buildEnvironment.CMake --preset win-amd64-v4 "-DPYTHON_EXECUTABLE=$(Get-PinyonPython)"
& $buildEnvironment.CMake --build out/build/win-amd64-v4 --target pinyon_shift
```

At runtime the v4 executable applies the patches while loading. It mounts
`<state>/title-update-v4` as `update:`; `--install <state-root>` on the
verifier below fills that folder, but only after every page verifies.
`config/rexglue/analysis-v4/` is generated by `tools/port-fh1-v4-analysis.py`,
and `src/fh1_v4_addresses.inc` by `tools/generate-fh1-v4-addresses.py`. Both
need image dumps in `.local/game/v4-images` (`<module>.base.bin` and
`<module>.v4.bin`), made with the archive extractor's `--xex-image` mode (add
`--apply-patch` for v4).

To verify your own package and extracted base executables without installing
the update, use the configured build environment:

```powershell
. .\tools\release-common.ps1
$buildEnvironment = Enter-PinyonBuildEnvironment
& $buildEnvironment.CMake --build out/build/win-amd64-release `
  --target pinyon_shift_fh1_archive_extract
& (Get-PinyonPython) tools/verify-fh1-title-update.py `
  'C:\path\to\title-update-folder-or-package' --base-root 'C:\path\to\extracted-disc'
```

Exact package and member hashes are pinned in
`config/supported-title-updates.json`. The verifier reads the package through
the SDK's STFS reader into a temporary directory. It applies each patch with
the SDK loader and checks every page against the patched hash chain and the
pinned image hash. Signature, version and media-ID fields are reported for
information only. It reports JSON and exits nonzero for an unknown package or
a base it does not apply to. A compatible result does not mean the v4 build is
qualified. The package includes 918 media files
and executable patches, but no separate DLC packages. Neither the disc, the
base build nor the AppData save is modified.
