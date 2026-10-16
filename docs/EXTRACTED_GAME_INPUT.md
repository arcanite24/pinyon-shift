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

On Linux and macOS (`pinyon.py setup`), the Games on Demand release of the
same build is accepted too: its three executables and the dashboard art
package (`nxeart`) are re-signed and hash differently, and are listed as the
`games-on-demand` revision in `config/supported-dumps.json`; all other files
match the disc catalog. The four files must all come from one release. The
Windows launcher and `verify-extracted-game.ps1` still accept only the disc.

The catalog was generated from a fresh extraction of the exact supported ISO.
A folder match identifies those game files; it does not claim to establish the
whole-file hash of an ISO that was not supplied. Setup copies verified game
files into its local build cache and never changes the source folder. A
separate existing cache can be replaced; keep the source outside that cache.
