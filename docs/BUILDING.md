# Building

The supported build environment is 64-bit Windows 10 or 11 with PowerShell 5.1
or newer, a DirectX 12-capable GPU, an internet connection, and about 25 GB of
free disk space.

Run:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso
```

The script performs five reproducible stages:

1. verifies the exact ISO size and SHA-256 against `config/supported-dumps.json`;
2. installs Visual Studio Build Tools when missing and downloads pinned portable
   tools whose hashes are recorded in `config/release-toolchain.json`;
3. clones the pinned ReXGlue revision and applies `patches/rexglue` in order;
4. extracts the disc and generates translated source under `.local/`; and
5. configures and compiles `out/build/win-amd64-release/pinyon_shift.exe`.

The original ISO is opened read-only and is never changed. Setup can be safely
run again after a failure; completed downloads and extraction are reused after
verification. Everything produced from the disc is ignored by Git.

To verify only the image:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso -VerifyOnly
```

To rebuild after changing host code or patches:

```powershell
.\tools\build-preview.ps1
```

To build the distributable launcher package:

```powershell
.\tools\package-launcher.ps1
```

That package contains a self-contained launcher executable and a source archive.
It deliberately excludes the compiled preview, generated translations, and all
game content.
