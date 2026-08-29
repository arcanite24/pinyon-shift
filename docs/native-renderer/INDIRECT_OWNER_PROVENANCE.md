# Indirect-owner provenance

This NR-05A milestone traces the four constructor-caller functions that
accounted for every known-origin draw in the preceding AppData qualification.
It adds one exact caller layer above packet construction. It remains passive
engine-structure discovery: the layer is not yet a mesh, material, object,
instance, streaming, or lifetime owner, and it does not authorize suppression.

## Static owner graph

The generated-title scanner proves five direct constructor edges inside the
four selected functions:

| Constructor caller | Constructor callsite(s) | Operational evidence |
| --- | --- | --- |
| `82409668` | `82409834` -> `82409398` | Builds or queues one indirect command list while updating device-side counters and synchronization state. |
| `824167F8` | `82416894` -> `82416A00` | Selects one of two device-held command-list sources and forwards its buffer field. |
| `8246E8F8` | `8246E92C` -> `82416A00` | Locks a context, submits the context's buffer field, then runs a follow-up operation. |
| `829F5FF0` | `829F6304`, `829F6338` -> `82409398` | Walks a tagged command stream and emits indirect work for two command forms. |

These names describe instruction-level behavior only. None proves a semantic
Forza render family.

The same scan proves 32 direct callsites into this layer:

| Constructor caller | Direct callsites | Distinct callers |
| --- | ---: | ---: |
| `82409668` | 7 | 5 |
| `824167F8` | 23 | 10 |
| `8246E8F8` | 1 | 1 |
| `829F5FF0` | 1 | 1 |

Every edge carries its exact callsite and return address. The inventory also
records bounded local `r3-r10` definitions at all 38 constructor callsites and
all 32 owner callsites. Constructor calls expose 142 locally proved argument
definitions, including 27 direct memory loads; 158 slots stop at an
intervening call. Owner calls expose 112 locally proved definitions, including
35 direct memory loads; 138 slots stop at an intervening call. The remaining
slots are unchanged entry registers. These are object/context leads, not
pointer, type, or lifetime proof.

## Runtime contract

Each selected function has a balanced entry and exit hook. Entry runs after
the opening `mflr`, capturing the exact direct caller return address and
`r3-r10` in a 32-entry thread-local stack. Exit runs before stack restoration
and pops only the matching function. Entry, exit, open-at-shutdown, overflow,
underflow, and mismatch accounting is independent from the existing
constructor stack.

When one of the five proved constructor callsites enters its constructor, the
active owner is copied only if its exact function matches the static immediate
caller for that constructor return address. Missing or mismatched selected
owners are counted and fail closed. Other constructor callsites remain
explicitly without owner origin; no nearby or recently active owner is used.

The owner function, owner return address, and owner `r3-r10` sample follow the
same exact physical packet generation through indirect-buffer execution into
prepared-draw command-buffer lineage. The bounded lineage key now contains:

- exact constructor store, or `unknown`;
- exact constructor return address, or `unknown`;
- exact owner function and return address, or `unknown`; and
- indirect-buffer nesting depth.

Each class reports independent constructor and owner argument-varying masks.
This divides a constructor callsite only when its proved upstream owner
callsite differs; it cannot merge or infer unknown ownership.

## Promotion gate

The deterministic report requires:

- balanced owner `entries = exits + open at shutdown` accounting;
- zero owner stack faults;
- zero constructor-to-owner mismatches;
- an exact static owner-callsite resolution for every resolved runtime owner;
- the existing constructor, packet-generation, command-buffer, and safety
  gates; and
- explicit resolved, unresolved, and absent owner-origin coverage.

## AppData qualification

The completed batch was qualified once against the installed `0.1.0` AppData
save in session `20260829T152644Z-p16152`, using Release executable SHA-256
`077F1AE45FD5D4E1F353A456B620B8B3223C2C76D2693F1FFC43059D8FB40DE1`.
The 214.05-second run entered the live festival autoshow scene and exited
normally. Visual inspection confirmed the player car, crowd, stage structures,
sky, lighting, HUD, and event prompt remained intact.

The deterministic report completed with:

- 2,401,715 indirect draws and 2,201,749 prepared draws;
- 416,582 balanced constructor entries and exits, with zero open invocations
  and zero constructor stack faults;
- 390,818 balanced owner entries and exits, with zero open invocations and
  zero owner stack faults;
- zero constructor-to-owner mismatches;
- 1,669,534 owner-origin draws, all resolved to exact static constructor and
  owner callsites, with zero unresolved owner-origin draws; and
- zero invalid lineages, capacity overflow, packet-address failures, or packet
  table overflow.

Ten of the 32 statically proved owner callsites fed live festival draws:

| Owner function | Live direct caller return(s) | Owner-origin draws |
| --- | --- | ---: |
| `82409668` | `8240D1B0` | 372,058 |
| `824167F8` | `823F6BAC`, `824170BC`, `8241A2A4`, `824399F0`, `8243CE0C`, `8244CBF4`, `8244DD5C`, `8244E2A8` | 711,558 |
| `8246E8F8` | `824726F4` | 30,715 |
| `829F5FF0` | `829F6608` | 555,203 |

The performance capture contained 7,111 samples, with a 30.466 FPS median,
19.469 FPS one-percent low, 59.977 Hz host presentation cadence, zero present
deadline misses, and zero XMA stalls. The JSONL ended with
`process.shutdown`; no fatal, crash, device-loss, assertion, unhandled
exception, or unexpected-shutdown marker was present.

This promotes owner-callsite provenance as an exact operational classifier.
The observed argument variation supplies bounded leads for the next discovery
batch, but still does not establish object identity or lifetime ownership.

## Safety boundary

The hooks observe registers and packet addresses only. They read no guest
resource payload, mutate no guest state, alter no control flow, add no native
draw, and expose no suppression API. Xenos remains authoritative and all
semantic identities remain `unknown`.
