# Use an extracted game folder

The launcher accepts **Choose extracted folder** alongside **Choose ISO**.
Choose the directory containing `default.xex`, the two facade executables,
and the `media` directory. You can also drop that folder onto the launcher.
Confirm ownership, then build as usual.

Command-line setup:

```powershell
.\tools\setup-preview.ps1 -ExtractedPath 'D:\Games\Forza Horizon'
# -GamePath and -GameDir are aliases for -ExtractedPath.
```

Check a folder without provisioning tools, copying files, or building:

```powershell
.\tools\setup-preview.ps1 -ExtractedPath 'D:\Games\Forza Horizon' -VerifyOnly
.\tools\verify-extracted-game.ps1 -ExtractedRoot 'D:\Games\Forza Horizon' -Json
```

Only the supported USA retail base revision (MS-2505) is accepted. Every
expected file must have the cataloged size and SHA-256 hash. Missing, modified,
extra, or linked game files are rejected before building. The disc's
`$SystemUpdate` directory is ignored, as it is during ISO extraction.

The catalog was generated from a fresh extraction of the exact supported ISO.
A folder match identifies those game files; it does not claim to establish the
whole-file hash of an ISO that was not supplied. Setup copies verified game
files into its local build cache and never changes the source folder. A
separate existing cache can be replaced; keep the source outside that cache.
