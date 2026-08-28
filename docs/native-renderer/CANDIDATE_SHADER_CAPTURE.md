# Candidate shader capture

NR-02 now has a bounded, process-scoped path from an authentic ReXGlue D3D12
translation to the deterministic local shader-pack format. This is capture
tooling only. It does not replay a draw, suppress guest work, or change the
authoritative Xenos output.

## Capture seam

ReXGlue patch `0050-d3d12-shader-translation-observer.patch` adds a default-null
observer after `TranslateAnalyzedShader` has produced a valid host container.
The borrowed callback view contains only:

- vertex or pixel stage;
- the 64-bit guest shader hash;
- the exact 64-bit ReXGlue modification key; and
- the validated host bytecode container.

Invalid translations never reach the observer. With no observer registered,
the path performs one null callback check per newly translated shader. The
observer cannot change translation results, pipeline state, draw submission,
resolve behavior, or presentation.

## Local-only capture contract

Capture is enabled only when the process receives an explicit
`PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR`. The title-side writer rejects paths
that are not absolute or do not contain a `.local` component. Each capture is
limited to 256 unique identities, 16 MiB per container, and 128 MiB total.
Inputs must begin with the D3D container magic `DXBC`; all writes use temporary
files followed by replacement.

The writer produces `shader-manifest.json` and an `dxil/` directory. The
manifest uses `pinyon-shift.native-shader-pack.v1`, records SHA-256 for every
container, and is directly consumable by `tools/native-shader-pack.py`. Guest
hashes, specialization masks, file paths, and bytecode never enter diagnostic
logs or support bundles. `.dxil`, `.dxbc`, and `.pnsp` remain forbidden public
repository extensions.

Run an AppData-backed capture with:

```powershell
.\tools\capture-native-renderer-shaders.ps1
```

The helper verifies the installed `ForzaProfile` save, refuses to launch over
an existing Pinyon Shift process, creates a timestamped directory below
`.local/native-renderer/captures`, and delegates gameplay to
`tools/launch-preview.ps1` with the exact installed preview state root. It does
not copy, move, reset, or overwrite the save.

After closing the game, build and verify the captured pack locally:

```powershell
$capture = '.\.local\native-renderer\captures\<timestamp>'
python .\tools\native-shader-pack.py build `
  "$capture\shader-manifest.json" --output "$capture\captured.pnsp"
python .\tools\native-shader-pack.py verify "$capture\captured.pnsp"
```

## Qualification

The clean 50-patch build produced executable SHA-256
`C32EFE369AD59DCED9BD151BE90B3ECDC272D4C96A90F49D4865593F46191A44`.
All 69 repository tests passed, tracked Markdown links were valid, and the
public-source boundary reported zero violations. The ReXGlue unit suite passed
2,282 assertions across 247 test cases with four documented skips; the PPC
suite passed 6,549 assertions across 1,480 test cases.
AppData-backed session `20260828T030228Z-p10520` exited normally after capturing
34 authentic front-end translations: 14 vertex and 20 pixel containers,
407,148 bytecode bytes total. No callback was duplicated or rejected. The
generated 34-entry pack verified independently at 409,736 bytes with SHA-256
`259982B4F4D966A08041B699468A2CC66744E54606D9D98809B8829A746BEC1B`.

Xenos remained the sole output authority. The session recorded no capture
failure, device removal, TDR, resource-state warning, validation warning, or
presentation deadline miss. Presentation cadence was 60.005 Hz and simulation
cadence was 29.437 Hz. A separate default session
`20260828T030355Z-p41808` emitted zero shader-capture events, retained Xenos
authority, and exited normally with no error event. Neither run modified or
copied the AppData save.

This closes the local extraction/translation prerequisite for NR-02. Selecting
one stable candidate shader pair still depends on a scene-specific draw census;
geometry, constants, resources, and PSO state remain NR-02B through NR-02D.
