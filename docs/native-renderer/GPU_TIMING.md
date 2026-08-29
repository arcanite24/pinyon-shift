# Native renderer GPU timing

NR-04C requires separate GPU evidence for the preserved guest frame, private
native composition, and native output selection. RenderDoc remains useful for
resource and image inspection, but its F12 capture boundary did not reliably
contain the command-processor markers. Patch
`0070-d3d12-native-gpu-timing.patch` therefore records these buckets directly
with D3D12 timestamp queries.

## Collection model

The command processor owns a bounded three-frame timing ring. Each active slot
uses five timestamp queries:

1. guest-frame start;
2. guest-frame end and native-composition start;
3. native-composition end;
4. native-selection start; and
5. native-selection end.

The queries are resolved to a persistently mapped readback buffer on the same
command list as the measured work. A slot is consumed only after the existing
submission fence retires it. Collection never waits for the GPU; if every slot
is still in flight, the frame increments `native_gpu_timing_drops` and proceeds
without a timing sample.

The buckets mean:

- `guest_frame_gpu_time_ns`: preserved Xenos command-processor work before the
  native callback;
- `native_composition_gpu_time_ns`: construction of the private native display
  target;
- `native_selection_gpu_time_ns`: the native-to-guest output copy and barriers.

Selection samples are intentionally absent in `comparison_xenos`, because that
mode never writes the private target into guest output.

## Performance capture schema

The runtime CSV includes cumulative time and sample counters for all three
buckets plus the dropped-sample counter. `tools/summarize-performance.py`
accepts the timing fields only as a complete set and reports per-sample mean
microseconds. Older captures without any of the fields remain supported;
partially populated schemas fail closed.

## AppData qualification

Both comparison modes used the same clean binary
`B4F823DB76742FB8A95A877AE8A34F58BD1F0BD4820EC4E6B898A7FEECBBEE8D`,
the installed AppData save, the `open_world_day` marker, isolated draw
`1D253A52B55C9FB3`, and pass anchor `747837906D0BF484`.

| Mode | Session | Guest frame | Native composition | Native selection | Drops |
| --- | --- | ---: | ---: | ---: | ---: |
| `comparison_native` | `20260829T015610Z-p25896` | 32,604.962 us | 90.184 us | 20.682 us | 0 |
| `comparison_xenos` | `20260829T015923Z-p23056` | 34,848.473 us | 73.845 us | n/a | 0 |

The native-selected run collected 1,984 guest samples and 1,985 composition
and selection samples over 5,548 measured frames. It displayed the partial
retained native target and continuously reported native output authority. The
Xenos-selected run collected 1,892 guest samples and 1,893 composition samples
over 5,243 measured frames. It displayed the complete Xenos scene and correctly
recorded zero selection samples. Both runs reported zero presentation deadline
misses, no timing drops, and no device removal, TDR, or output-state fault.

Local machine-readable summaries are retained below `.local/qualification` as
`nr04c-gpu-timing-native-summary.json` and
`nr04c-gpu-timing-xenos-summary.json`.

## Safety boundary

Timing changes observation only. Renderer selection remains restart-gated and
default-off, Xenos draws and guest side effects remain preserved, and no draw
or resolve suppression API is introduced. Startup, stale, unsupported, or
failed native frames continue to yield to Xenos. These measurements close the
NR-04C timing-evidence gap; they do not establish visual coverage or authorize
NR-04D suppression by themselves.
