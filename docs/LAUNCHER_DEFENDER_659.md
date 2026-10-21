# Launcher Defender detection (#659)

The official Windows 0.5.1 package reproduces `Trojan:Win32/Yomal!rfn` on
multivac on 2026-10-18. The report is confirmed; whether it is an incorrect
detection remains for Microsoft to determine. Do not advise players to disable
protection, allow the threat, add an exclusion or restore a blocked sample.
The flagged official launcher was not executed, and no manual vendor submission
was made.

## Artifact identity

The hash in [#659](https://github.com/arcanite24/pinyon-shift/issues/659)
identifies **PinyonShift-Launcher.zip**, rather than a standalone DLL.
The download from the [official 0.5.1 release](https://github.com/arcanite24/pinyon-shift/releases/tag/v0.5.1)
matches the [release API asset digest](https://api.github.com/repos/arcanite24/pinyon-shift/releases/tags/v0.5.1).
Asset ID `634420626` was created on 2026-10-12 at 17:09:06 UTC, last updated
at 17:09:09 UTC, and is 67,357,233 bytes. The ZIP contains only the EXE and
the source payload ZIP.

| File | SHA-256 |
| --- | --- |
| Release ZIP | `88841e7741d2750fefea58400a4c28c972379b1080d6c0c3cd726001bd03d5d6` |
| `PinyonShiftLauncher.exe` (71,928,970 bytes) | `5cf66302d9be3186116840142d154f03057e1799c5f2dc44c4d751a5c3e446fc` |
| Bundled `PinyonShiftLauncher.dll` (501,248 bytes) | `085951029accf97f00a1b483425f6fa140cde7f865c9b6a4926f04415402c0a2` |
| `pinyon-shift-source.zip` | `645ca9721ff5a3fd019667dde5122bffd5f724014415e5a2401d57c258f22d8d` |

The EXE and DLL hashes were computed by reading the ZIP and bundle in memory,
without loading any assembly. Defender blocked a normal read of the extracted
EXE; protection was left in place. The managed DLL is compressed to 326,126
bytes in the EXE. The bundle has 448 entries. Microsoft's
[bundle manifest](https://github.com/dotnet/runtime/blob/v8.0.22/src/installer/managed/Microsoft.NET.HostModel/Bundle/Manifest.cs)
and [file entry format](https://github.com/dotnet/runtime/blob/v8.0.22/src/installer/managed/Microsoft.NET.HostModel/Bundle/FileEntry.cs)
describe how the inventory was read.

The packaged provenance names clean source commit
`a72a92a5f215a32875386b824b8b6f0f34e1caf9`, matching tag `v0.5.1` and
[release workflow run 38281836388](https://github.com/arcanite24/pinyon-shift/actions/runs/38281836388).
All 300 other source-payload files match that tag after normalizing CRLF to LF.
This checks the payload; it does not prove the EXE was built from those sources.

The latest published Windows package at the time of this check is **0.6.0**,
asset `651553048`, published 2026-10-17 at 20:44:35 UTC. Its 67,541,966-byte ZIP
matches the [latest release API digest](https://api.github.com/repos/arcanite24/pinyon-shift/releases/tags/v0.6.0)
and its normal custom scan reported no threats with the intelligence recorded
below. This is a separate artifact, not a determination about 0.5.1.

| 0.6.0 file | SHA-256 |
| --- | --- |
| Release ZIP | `d4996a1355f8d9bcb196f17e05d398d0c9ed08decbafba2b7ae510c173993ba3` |
| `PinyonShiftLauncher.exe` (71,940,716 bytes) | `55edd8b125eb2c7045a1377c54ea840f5f7ebc83729184e5991de71fc6703632` |
| Bundled `PinyonShiftLauncher.dll` (527,360 bytes) | `1a068e00c0f0c4bae2c08f914899b6ad788277e12826127fcc86c0292481a6cf` |

## Publish inputs and dependency check

At the release tag, the WPF project targets `net8.0-windows`, has no explicit
`PackageReference`, and publishes a self-contained `win-x64` single-file app
with compression, native-library extraction and embedded debug symbols.
The application manifest requests `asInvoker`. `tools/package-launcher.ps1`
publishes from source, sets release/file versions, creates the source payload
and ZIP, and does not sign the Windows EXE. The release workflow packages on
`windows-latest`; it does not pin a Windows .NET SDK or run an antivirus scan.

The bundled dependency manifest identifies .NET and Windows Desktop runtime
packs **8.0.31**. All **445** bundled entries other than the launcher's DLL,
dependency manifest and runtime configuration match files in these NuGet
packages byte for byte after decompression:

| Package from `api.nuget.org/v3-flatcontainer` | Package SHA-256 |
| --- | --- |
| `microsoft.netcore.app.runtime.win-x64.8.0.31.nupkg` | `1504ead20c9a25e4c47ece56b6cd407697ea0cde0148e07e71bebc1e2d841c2f` |
| `microsoft.windowsdesktop.app.runtime.win-x64.8.0.31.nupkg` | `f2d14397e990f3c39efb325abd6d6430312a16a3c4596a55fb10b36c8fdcbd33` |

`dotnet nuget verify <package> --all` passed for both packages, reporting
Microsoft Corporation author signatures and NuGet.org repository signatures.
This checks the bundled runtime dependencies, not the launcher's own code,
native host, future setup downloads or the full release supply chain.
Setup tool archive hashes and the ShiftGlue revision are recorded separately
in `config/release-toolchain.json`; those tools are not bundled DLLs.

## Defender reproduction and packaging comparison

Windows build 26200 on multivac, Defender in Normal mode, antivirus and
real-time protection enabled throughout. Engine `1.1.26090.9`, platform
`4.18.26090.9`, intelligence `1.461.84.0` (updated 2026-10-17 18:31:20 UTC-6).
A normal `MpCmdRun.exe -Scan -ScanType 3 -File <absolute-path>` custom scan
of the official ZIP reported **one threat**. Protection history recorded
threat ID `2147927549`, `Trojan:Win32/Yomal!rfn`, and a resource path ending
in `PinyonShiftLauncher.exe->PinyonShiftLauncher.dll-[DotNetCompressed]`.
`DidThreatExecute` was false.

A standard security intelligence refresh produced no output within six minutes;
its command-line helper was stopped while the Defender service and real-time
protection remained enabled. These scans use the recorded intelligence version
above, rather than a verified latest version.

The command returned **0 despite reporting a threat**. Microsoft's
[command reference](https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus)
documents that 0 can also mean successful remediation. A future release scan
must inspect the output and detection records; testing the exit code alone
would accept this sample. No Defender settings, exclusions or allowed threats
were changed, and no quarantine restore was attempted.

Local publishes used .NET SDK **8.0.416** and Release/win-x64/self-contained
settings, release version 0.5.1, without executing the published programs:

| Source and publish variant | EXE bytes | Custom scan |
| --- | ---: | --- |
| Official 0.5.1 download, compressed, runtime 8.0.31 | 71,928,970 | Yomal detection |
| Official 0.6.0 download, compressed, runtime 8.0.31 | 71,940,716 | No threats reported |
| Tag `v0.5.1` rebuilt, compressed, runtime 8.0.31 | 72,000,958 | No threats reported |
| `dev` `45d1739`, compressed, runtime 8.0.22 | 72,044,730 | No threats reported |
| Same `dev` publish, compression disabled, runtime 8.0.22 | 162,443,247 | No threats reported |

The two `dev` variants contain the identical managed launcher DLL hash
`2855024f98b4fe8da11d09db556e23172ba78779aaa191b9a08a0c6d30f86d1a`.
The tag rebuild's DLL hash is
`2a7f746c29cfba57f3eef8bf3f8457a0728c0fb860feabd73d79485d62e0ebf9`;
it is **not** a byte-identical reproduction of the release. SDK/build paths
and embedded debug data differ; a scan of a rebuild cannot clear the archived
sample. Likewise these local results do not qualify the next CI artifact.

Compression was left unchanged: both local variants scanned without threats,
so this experiment provides no evidence that removing compression fixes the
reported alert, while it increases the local EXE from 72.0 to 162.4 MB.
Code signing would establish publisher identity; it does not establish a
malware verdict. An Authenticode comparison needs a maintainer-controlled
certificate and was not performed. Do not substitute a self-signed certificate
or change packaging just to get a different detection result.

## Maintainer submission draft

The maintainer should use Microsoft's
[sample submission portal](https://www.microsoft.com/en-us/wdsi/filesubmission),
select **Software developer**, and request review of the suspected incorrect
detection. Microsoft describes the process in its
[submission guide](https://learn.microsoft.com/en-us/defender-xdr/submission-guide).
Submit the exact official release ZIP if the portal accepts it, with the DLL
and EXE identities above; a locally rebuilt launcher is a different sample.
If protection prevents attaching it, record that and use Microsoft's supported
submission guidance rather than restoring or excluding it to complete these steps.

Suggested description:

> Pinyon Shift's official Windows 0.5.1 launcher ZIP reproduces
> Trojan:Win32/Yomal!rfn. The release ZIP SHA-256 is
> 88841e7741d2750fefea58400a4c28c972379b1080d6c0c3cd726001bd03d5d6.
> Defender identifies PinyonShiftLauncher.dll inside the compressed .NET
> single-file EXE. It is a WPF launcher which extracts our source payload,
> provisions build tools and builds the game locally from the player's disc.
> We request analysis of a suspected incorrect detection; we have not
> established that the archived binary is safe. The reproduction, component
> hashes, source tag and runtime dependency checks accompany this report.

Attach the release URL/API metadata, scan output, affected Protection history
entry, Defender versions and this investigation. Record the submission ID and
Microsoft's final determination on #659 before calling it a false positive or
resolved. Recheck the exact archived sample and next official CI artifact
with current intelligence, preserving hashes and output for each. If the
reporter's local scan still differs, request their intelligence version,
detection time and affected resource path. Do not ask for their save or disc.
