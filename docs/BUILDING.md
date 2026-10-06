# Building

The supported build environment is 64-bit Windows 10 or 11 with PowerShell 5.1
or newer, a GPU with Vulkan 1.3 (the default graphics API) or Direct3D 12, an
internet connection, and about 25 GB of free disk space.

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
5. configures and compiles `out/build/win-amd64-release/pinyon_shift.exe`, with
   both the Vulkan and the Direct3D 12 backends; and
6. when Direct3D 12 is the chosen graphics API, prepares its shader packs from
   your local game files and validates them in a hidden, muted startup run
   before enabling play. Vulkan, the default, translates shaders as the game
   runs and needs no preparation.

For Direct3D 12 the launcher also checks graphics on every launch, including
existing installs. Valid artifacts are reused; missing, damaged or outdated
artifacts are prepared automatically for the selected resolution and graphics
driver. Preparation uses
separate temporary game states and never copies or resets your save. If it is
interrupted, reopening the launcher retries it. No shader commands are needed.

The original ISO is opened read-only and is never changed. Setup can be safely
run again after a failure; completed downloads and extraction are reused after
verification. Everything produced from the disc is ignored by Git.

To verify only the image:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso -VerifyOnly
```

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
everything in a `data` folder beside it; see "Portable install" in the README.
