# Indirect-producer provenance

This NR-05A milestone adds one exact upstream layer above the three dominant
live indirect owners. In the preceding AppData qualification, those owner
callsites accounted for 1,420,568 of 1,669,534 owner-origin draws (85.1%). The
layer remains passive structural evidence: it does not identify a render
family, object type, instance, resource lifetime, or suppression candidate.

## Static producer graph

The generated-title scanner proves seven direct calls into the selected
producer functions:

| Producer | Direct caller callsite(s) | Owner callsite | Prior draw coverage |
| --- | --- | --- | ---: |
| `8240D070` | `823EA6F0`, `8240CFFC` | `8240D1AC` -> `82409668` | 372,058 |
| `82417060` | `82418A24`, `82418EC8`, `82437044`, `82DE8DBC` | `824170B8` -> `824167F8` | 493,307 |
| `829F6360` | `829F67AC` | `829F6604` -> `829F5FF0` | 555,203 |

Every edge records its exact callsite and return address. At each producer
call, `r3` is copied from a nonvolatile register (`r31`, `r24`, `r25`, `r20`,
or `r28`). Other locally visible `r4-r10` definitions are retained, while
values crossing an intervening call remain explicitly unknown. These are
bounded object/context leads only; no pointer validity, identity, type, or
lifetime is inferred.

## Runtime contract

The selected producers have balanced entry and exit hooks. Entry captures the
direct caller return address and `r3-r10` in an independent 32-entry
thread-local stack. Exit pops only the matching producer. Entries, exits,
open-at-shutdown invocations, overflow, underflow, and mismatches are counted.

An owner inherits producer provenance only when its exact owner return address
maps to one selected producer and the active producer function matches that
static edge. Missing producer context remains absent; a wrong active producer
is counted as a mismatch and fails closed. The producer function, return
address, argument sample, and varying mask then follow the already exact
owner, constructor, packet-generation, indirect-execution, and prepared-draw
lineage. No recent or nearby context is substituted for an exact match.

The bounded lineage key now contains constructor store and return, owner
function and return, producer function and return, and indirect-buffer depth.
Unknown values remain distinct and explicit.

## Promotion gate

The combined deterministic report requires:

- balanced producer `entries = exits + open at shutdown` accounting;
- zero producer stack faults and zero owner-to-producer mismatches;
- exact static resolution for every runtime producer origin;
- the existing owner, constructor, packet-generation, command-buffer, and
  safety gates; and
- explicit resolved, unresolved, and absent producer-origin coverage.

## AppData qualification

The completed batch was qualified once against the installed `0.1.0` AppData
save in session `20260829T155036Z-p13876`, using Release executable SHA-256
`6BF13B9169CC8EDA45661B51D27CA304CE311129FFF85500600FEF553B234B22`.
The 380.52-second capture advanced through the title into the live festival
scene and exited normally. Visual inspection confirmed the player car, crowd,
stage structures, sky, lighting, HUD, and autoshow prompt remained intact.

The deterministic report completed with:

- 6,880,926 indirect draws and 6,463,454 prepared draws;
- 967,815 balanced producer entries and exits, with zero open invocations and
  zero producer stack faults;
- zero owner-to-producer mismatches;
- 4,400,708 producer-origin draws, all resolved to exact static constructor,
  owner, producer, and producer-caller callsites;
- zero unresolved producer-origin draws; and
- zero invalid lineages, capacity overflow, packet-address failures, packet
  table overflow, constructor faults, or owner faults.

Five of the seven statically proved producer callsites fed live festival draws:

| Producer | Live caller return | Static caller | Producer-origin draws |
| --- | --- | --- | ---: |
| `829F6360` | `829F67B0` | `829F6620` | 2,049,909 |
| `82417060` | `82437048` | `824365B0` | 1,755,152 |
| `8240D070` | `8240D000` | `8240CF68` | 499,163 |
| `82417060` | `82418ECC` | `82417BC0` | 96,454 |
| `82417060` | `82418A28` | `82417BC0` | 30 |

The performance capture contained 11,968 samples, with a 30.143 FPS median,
19.515 FPS one-percent low, 59.994 Hz host presentation cadence, one present
deadline miss, and zero XMA stalls. The JSONL ended with `process.shutdown`;
no fatal, crash, device-loss, assertion, unhandled-exception, or unexpected-
shutdown marker was present.

This qualifies producer-caller provenance as an exact operational classifier.
The observed caller and argument variation can nominate a later object/lifetime
investigation, but it does not establish semantic identity on its own.

## Safety boundary

The hooks observe registers and packet addresses only. They read no guest
resource payload, mutate no guest state, alter no control flow, add no native
draw, and expose no suppression API. Xenos remains authoritative and all
semantic identities remain `unknown`.
