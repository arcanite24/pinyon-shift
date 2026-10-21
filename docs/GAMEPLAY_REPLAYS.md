# Gameplay replay persistence research (#492)

Gameplay replay persistence and offline video export are not implemented.
The post-race player is a different system from the whole-session scheduler
experiments in [CLEAN_SLATE_RESEARCH.md](CLEAN_SLATE_RESEARCH.md). Neither those
experiments nor GPU frame replay proves that a gameplay replay survives a
restart. A recording's two stream objects alone are not a complete saved replay.

## Base-disc contract identified so far

These are observations of the player's locally translated base executable,
not a replacement for its implementation. The addresses are **base only**;
v4 layouts and runtime behavior still require qualification.

| Object or operation | Contract and evidence |
| --- | --- |
| Replay manager | `sub_82E42F50` creates a 600-byte object, constructs it with `sub_82E42E20` and publishes its address at `0x834B35E4`. Its vtable is `0x82249498`. |
| Stream registry | Manager +412 is a tree with sentinel pointer at +416 and count at +420. Nodes have left/parent/right links at +0/+4/+8, an ID at +12, stream pointer at +16, mode at +20, kind at +24, name at +32 and parent stream ID at +64. The sentinel flag is +69. `sub_82E3D3B0` looks up an ID; `sub_82E41288` creates a root stream and `sub_82E41358` attaches a child. |
| Recording component | `CRecordReplayComponent`'s start (`sub_82632368`) creates the `Replay` stream from `replay_stream`, kind 0, then its child from `replaydata`, kind 2. The component stores their IDs at +8/+12. These are IDs, not buffer addresses. |
| Stream object | `CReplayStream` has vtable `0x822493EC`, a time anchor float at +8, an IOSys backing stream at +12 and an offset index vector at +24/+28/+32. Recording/playback start writes the anchor (`sub_82E3B598`, `sub_82E3B5F8`); it is not the current playback position. The meaning of its byte at +16 is not yet fully qualified; the probe reports it without assigning a format meaning. |
| Stream modes | Creating a stream records mode 1. `sub_82E41620` changes it to 2 and calls the recording-start operation; `sub_82E416F8` changes it to 3 and calls the playback-start operation. `sub_82E43508` stops an active stream and resets its mode to 1. Loaded streams start in mode 0 (`sub_82E41480`). |
| Destruction | `sub_8262C048` stops and unregisters both recording streams, clears both component IDs and resets its time. A pointer or ID retained across this boundary is not a saved replay. |
| Native stream view | `sub_82E3BF20` (stream vtable +96) returns an IOSys stream view. It does not serialize the manager, initialization object or scene state. Its lifetime, cursor behavior and completeness must be measured before using it for host export. |
| Initialization | The `ReplayInitData` serializer is `sub_825A2D40`; `sub_825A56E0` reads initialization data. `sub_825563B8` takes both initialization and stream data into the replay-loading flow via `sub_8260E8E8`. Initialization includes the event/car setup; restoring stream bytes without it is incomplete. |
| Native combine/extract | `sub_82C82A58` combines two IOSys streams into a buffer with two length words followed by the stream bodies; `sub_82C83AC0` reconstructs views of those bodies. This is not yet a qualified host file format: bounds, ownership, endianness, initialization and cross-build compatibility need independent validation. |

The `savereplaytodevkit` option is a byte at launch-options +3208; the
recording component reads it when choosing its stream backing. The option
name does not establish a host save/load contract. Do not turn it on against
shared game media to discover where it writes. `savewmvtodevkit` (+4877) is
used by the old WMV path, not an FFmpeg exporter.

## Read-only live observation

`tools/inspect-fh1-gameplay-replay.py` reads the base-disc manager and stream
metadata with Windows `ReadProcessMemory`. It requests no write or suspend
permission, never calls guest functions and does not dump packet payloads.
It checks immutable base-disc vtable entries even before the manager exists,
and rejects unknown vtables, invalid bounds, cyclic trees and a tree changed
during sampling. Samples remain non-atomic: they cannot prove frame equality,
an immutable buffer or a valid restart image.

Run a route with `tools/run-fh1-render-test.py` and a pinned seed, holding the
`run-multivac` lock for the whole game/probe session. Observe that run's PID
and log, for example:

```powershell
python tools/inspect-fh1-gameplay-replay.py --pid <preview-pid> `
  --log <private-run>.state/logs/runtime.log --samples 240 `
  --output .local/replay-streams.jsonl
```

If Windows locks `runtime.log` while the preview runs, replace `--log` with
`--guest-base <virtual-base>` from its arena log line (for example,
`--guest-base 0x100000000`). The probe still checks the live manager and stream
vtables; an incorrect base cannot qualify a sample. Keep the observation
shorter than the route if a zero exit is needed: reads after process exit are
reported as unavailable, not counted as valid samples.

The output must be a new file. It contains metadata with schema
`pinyon-shift.gameplay-replay-probe.v1`, not a playable replay. A nonzero exit
means at least one sample failed; retain its error alongside successful
samples. A v4 process is deliberately rejected rather than read with guessed
offsets. No generated translation, process dump or game data belongs in git.

### Observed on multivac, 2026-10-18

The existing base Windows preview (SHA-256
`FC46C811D0970C419FD34EF9151216BDD50CDC6E3584E66AF001F4F85A551704`)
was run against a private copy of `appdata-2026-09-27` with the race-retire
inputs and the null GPU backend. Its sidecar claims root `80f93d1a+dirty` /
SDK `773539d4`, but its recorded executable hash does not match the binary;
host build provenance is therefore unqualified. The worktree used for static
analysis was root `fe0dcf1d` / SDK `3bb29938`; that is not proof of the running
binary's provenance. The runner completed all 12 capture markers, with game mode 3
during the race and mode 17 after retirement; no images were rendered. This
checks the probe and lifecycle, not the post-race player or video output.

The observer collected 133 valid live samples. During the race it saw root
ID 3 (`Replay`, kind 0), child ID 4 (`Replay - Side-Stream`, kind 2, parent 3)
and a separate ID 5 (`FullRaceGhost`, kind 1). All three used
`CWindowedStream` backing (vtable `0x8222C55C`); root and child later changed
to IDs 6/7 with `CCircularStream` backing (`0x8222B5AC`) on the return to free
roam. The anchor remained 25.692719 during repeated mode-2 observations: it
must not be used as an export clock. The final 27 requested samples happened
after the process exited and correctly returned unreadable-memory errors.

Artifacts remain private under `.local/replay-probe-null-run{,.state}` and
`.local/replay-probe-null-observations.jsonl`. The probe did not extract or
restore packet payloads, and this route retired the race instead of entering post-race
playback. The first persistence acceptance gate is still open.

## Remaining acceptance gates, in order

1. Observe a complete race, post-race playback, rewind/seek and exit. Correlate
   stream IDs/modes with the visible player, and identify initialization,
   packet framing, wrap order, lifetime and pending writes. A race-retire run
   does not qualify the post-race player.
2. Extract through the game's stream/initialization serializers at a verified
   quiescent boundary. Define a private host envelope with explicit version,
   executable/content identity, lengths, bounds and integrity checks; reject
   unsupported or truncated inputs before touching guest state. Do not dump
   guest object layouts or pointers as the persistence format.
3. In a new process and private state copy, reconstruct initialization and
   both streams through the game's loader. Compare car poses, camera/seek
   behavior and duration with the recording, including a wrapped recording.
   Repeat for v4 before claiming v4 support.
4. Step **only the replay player** on a rational output clock. Associate each
   completed guest presentation with a playback step, wait for GPU readback,
   and record a per-frame index and replay time. Generic wall-clock input
   routes and asynchronous F8 photo capture do not provide this guarantee.
5. Verify every `n / 60` replay time has exactly one captured frame, including
   slow rendering and seek boundaries. Only then encode that verified frame
   sequence with FFmpeg and check frame count and timestamps. Add the saved
   replay UI after the restart and cadence gates pass.
