# Indirect-constructor provenance

This milestone refines command-buffer ownership from an exact packet store and
nesting depth to the title function and direct callsite that created that packet
generation. It remains a passive discovery bridge. It does not identify a mesh,
material, render pass, or lifetime owner, and it does not authorize suppression.

## Static call graph

The dispatch scanner recognizes every direct `bl` targeting a function that
stores `PM4_INDIRECT_BUFFER` or `PM4_INDIRECT_BUFFER_PFD`. Against the verified
MS-2505 generated title it proves seven packet constructors in six functions
and 38 direct callsites:

| Constructor function | Store site(s) | Direct callsites | Distinct callers |
| --- | --- | ---: | ---: |
| `82409398` | `824095B4` | 7 | 6 |
| `82416A00` | `82416EFC` | 3 | 3 |
| `8246FB98` | `8246FC1C` | 21 | 14 |
| `8263BCB8` | `8263BD64` | 1 | 1 |
| `829E8E00` | `829E8E88` | 2 | 2 |
| `829EC400` | `829EC49C` | 4 | 1 |

Each inventory record contains the constructor function, stored packet opcode
and store sites, caller function, callsite, and return address. The return
address is the exact value available in `r12` after the constructor's opening
`mflr`, so static and runtime evidence join without timing or address-range
inference.

## Runtime contract

All six constructors have balanced entry and exit hooks. An entry hook runs
after the opening `mflr`, captures the constructor function, direct caller
return address, and bounded `r3-r10` entry metadata, and pushes it onto a
32-entry thread-local stack. The exit hook runs before guest stack restoration
and pops only the matching constructor. Overflow, underflow, mismatched exits,
and invocations open at shutdown are counted explicitly.

The existing packet-store hook copies the active constructor origin into the
same bounded packet generation that carries its exact physical PM4 header
address. Backend indirect-buffer execution still consumes only the oldest exact
retained generation for that address. A prepared draw inherits constructor
metadata only from the matching active indirect-buffer stack frame.

The lineage ownership key is now:

- exact constructor store, or `unknown`;
- exact constructor return address, or `unknown`; and
- indirect-buffer nesting depth.

Each class reports the statically resolved callsite and caller function when
available, a sample `r3-r10` vector, and an argument-varying mask. Unknown or
uninstrumented paths remain unknown; they are never assigned to a nearby or
recent caller.

## Qualification gates

The command-lineage report fails closed when a runtime constructor origin does
not map to the function that owns its store. A return address outside the
proved direct-call inventory remains exact runtime evidence but has an
unresolved static caller; resolved and unresolved draw coverage are reported
separately. The report also requires balanced constructor
entry/exit/open-at-shutdown accounting and zero constructor-stack faults.
Packets without a captured origin remain an explicit coverage metric, not an
integrity failure.

The static inventory passes with seven constructors, six functions, 38 direct
callsites, and the unchanged safety contract. Release executable
`346D15B8DF1E7D5D2AF97C93C711F021E5ABFC01B3B495F835778C94BE675A5C`
loaded the installed `0.1.0` AppData save through the title and menu into the
live festival scene. Session `20260829T150242Z-p23532` exited normally after a
156.947-second performance capture covering 5,160 samples.

The runtime report completed across 7,368,672 indirect draws and 7,144,490
prepared draws. All 1,438,652 constructor entries matched 1,438,652 exits,
with zero invocations open at shutdown and zero constructor-stack faults. The
packet table recorded 1,451,713 generations; 1,434,662 indirect executions
matched an exact retained generation, 10,486 generations were explicitly
evicted, and 6,565 remained retained at shutdown. Address failures, table
overflow, invalid lineage, and draw-stack faults were zero.

Constructor origin covered 6,020,430 draws. Every captured origin resolved to
a proved direct callsite, with zero unresolved constructor-origin draws and
zero matched packets lacking an origin. The remaining 1,348,242 draws stayed
in two explicit unknown-origin lineage classes rather than receiving inferred
ownership. All 1,766,527 indirect enters reconciled with 1,766,526 exits plus
one buffer open when the app was closed mid-frame.

Xenos remained authoritative, suppression remained disabled, and the log
contained no crash, fatal error, device loss, assertion failure, or unexpected
shutdown marker. The visually inspected festival scene retained the expected
car, crowd, structures, HUD, lighting, and sky. Median derived performance was
30.56 FPS and the 1% low was 19.227 FPS.

## Safety boundary

The hooks observe registers and packet addresses only. They do not read guest
resource payloads, mutate guest state, alter control flow, add a native draw,
or expose a suppression API. Xenos remains authoritative and suppression
remains disabled.

## Next ownership layer

The four immediate constructor callers that accounted for all known-origin
draws are now traced one exact caller layer upward. Their 32 proved direct
callsites, balanced runtime contract, and additional fail-closed gates are
documented in `INDIRECT_OWNER_PROVENANCE.md`. That work remains passive and
does not retroactively assign semantic identity to this qualified constructor
evidence.
