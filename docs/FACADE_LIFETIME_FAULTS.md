# Facade lifetime faults (#556 and #674)

These reports have different demonstrated failure paths. They do not justify
ignoring null writes or disabling speech/media jobs.

## Android stack reuse (#556)

The Pixel 3 XL report names Android 13 with Linux 4.9.337. The parent thread
faults writing guest `0x70830000`, with LR `0x881ED538`, in bionic `memset`.
`0x881ED4F0` is XMediaFacade's thread-creation wrapper; that return address
follows its `ExCreateThread` import. Both addresses are unchanged in v4
(normalized function match against the extracted base and v4 images).
This is thread creation on the parent, not a fault in a running child fiber.

`XThread::AllocateStack` reserves and commits a guest range, fills it, then
protects its guards. Reused stack ranges can still have inaccessible guards
from their previous owner. The POSIX allocator used `MAP_FIXED_NOREPLACE`
and accepted any successful `mmap` result. Linux before 4.17 can ignore that
flag and return a different address when the requested range already exists;
see [mmap(2)](https://man7.org/linux/man-pages/man2/mmap.2.html).
That leaves the requested guard inaccessible and leaks the relocated mapping.
It explains how stack initialization can fault despite successful allocation.

The allocator now rejects relocated results, unmaps them, and uses the same
existing-reservation commit path as an `EEXIST` result. Reserve-only
collisions still fail. No existing data is replaced and no guard is relaxed
outside the requested commit range. The SDK's `memory_posix_tests` intercepts
only its local `mmap` calls and strips the flag to reproduce the old-kernel
contract on a current kernel. It checks guard reuse, preserved data, no leaked
mapping, reserve-only collisions, and ordinary current-kernel commits.

The production backend passed 23 assertions on 4 KB WSL Linux. A separate
NDK-built ARM64 probe ran on an Odin 2 Portal (4 KB pages, Linux 5.15.123)
with `MAP_FIXED_NOREPLACE` deliberately ignored: the original backend
returned the wrong mapping, while the patched backend committed and wrote
the original guard. Only temporary executables were deployed; the installed
APK, settings and save were unchanged, and the probe files were removed.

Validation still needs a current Pixel 3 XL launch on the reporter's kernel.
The GPU budget warning is separate evidence and does not establish OOM as the
cause of this access violation.

## Windows unload/reload (#674)

The 0.6.0 report faults writing guest `0x00000006`, LR `0x82CC1B60`, after
XMediaFacade reload and SpeechFacade unload. Static analysis places that LR
after the virtual allocation call in `0x82CC1B10`. The allocator is selected
by the current guest thread ID through `0x82CBC390` and registry lookup
`0x82CBC348`; its registry starts at `0x8349F978`, with the selection gate
at `0x8349FDB4`. It is not a demonstrated speech callback at that LR.

Verified base-to-v4 mappings, using function/context and paired data loads:

| Base | v4 | Role |
| --- | --- | --- |
| `0x82CC1B10` | `0x82D83590` | allocation entry |
| `0x82CC1B60` | `0x82D835E0` | return from override allocation |
| `0x82CC1B58` | `0x82D835D8` | diagnostic hook before the override call |
| `0x82CBC390` | `0x82D7DE88` | current thread's allocation override |
| `0x82CBC348` | `0x82D7DE40` | registry search by guest thread ID |
| `0x8349F978` | `0x835950C8` | registry entries (ID, object pairs) |
| `0x8349FDB4` | `0x83595504` | active override scope count |
| `0x82CBD4F0` | `0x82D7EF70` | enter an allocator override scope |
| `0x82CBD598` | `0x82D7F018` | restore the preceding override |
| `0x834B49F8` | `0x835AA444` | allocator object observed in the base route |
| `0x82E5B7C8` | `0x82F1D3F0` | its virtual allocation target |
| `0x825576A8` | `0x825CB038` | allocation-entry tail alias (reported CTR) |
| `0x82441690` | `0x82471798` | current guest thread ID helper |

The reported CTR `0x825576A8` is only a tail jump to the allocation entry,
not the selected override implementation. Its v4 context match was checked
against the corresponding tail target. It cannot identify the failing
allocator by itself.

The registry's identity helper reads the KTHREAD pointer from PCR `+0x100`
and its thread ID at KTHREAD `+0x14C`, consistent with the SDK layout; it
does not use a module handle. The base/v4 helpers perform the same reads.

The scope entry takes a save slot and a new allocator. Under the registry
critical section it finds or adds the current guest thread ID, saves that
thread's previous allocator in the slot, installs the new allocator, and
increments the active-scope count. Scope exit restores the saved allocator
for the current thread and decrements that count. The count is not a
loaded-module reference count, and changing facade unload ordering without
identifying the active scope would not establish correct ownership. These
contracts and the two exact base/v4 function matches come from static analysis;
they do not prove a mismatched scope in the reported run.

The LANGUAGE row saves `user_language` and `user_country` to the private
state's configuration and requires a process restart. It does not update the
live cvars or cancel speech work. The five settings events in the report
therefore do not prove language asset reload caused the crash.

`config/render-tests/fh1-facade-transitions.fh1test` exercises free roam,
five actual PROFILE/LANGUAGE changes, return to title, reentry, and another
return to title. Run through `tools/run-fh1-render-test.py` with pinned seed
`appdata-2026-09-27` and `--include-opening-movies`. Its expectation checks
ordered load/unload pairs for both facades and the five settings events;
survival without reaching the transition cannot pass. The runner copies the
seed into a private per-run state.

On Windows, also pass
`--game-argument=--pinyon_shift_fh1_render_fps_limit=60`. The opening movies
take wall time, while the route sends input at output-frame numbers. On
multivac, an unlimited-output run of the integrated build reached SINGLE
PLAYER after its startup presses and correctly failed the facade-cycle gate.
The same route at 60 fps reached gameplay and completed both cycles. Keep
the cycle gate enabled; captures and normal process completion alone do not
prove that the facade lifetime was exercised.

The route also enables `PINYON_SHIFT_FACADE_LIFETIME_TRACE`. Immediately
before the override call, `facade.allocation_override` records the guest
thread ID, object, target, size and attributes when the object/target changes
or the request is at least 1 MiB. It reads only the registers already prepared
for the call, changes no guest state, and is off outside this diagnostic.

The allocator selected in the reported crash, its ownership and the faulting
instruction still need live evidence or the matching local crash dump. The uploaded diagnostics omit
the dump and contain no reproduction steps. A null-write suppression or a
speculative cancellation hook would hide this missing contract.

On multivac (Ryzen 7 5800X, RTX 4080), the existing baseline binary completed this
two-cycle route from the pinned seed without an access violation: five
LANGUAGE events, two speech loads/unloads and three media loads/two unloads.
Its embedded provenance reports `80f93d1+dirty` with SDK `773539d`; this
qualifies the route's reachability, not this branch or the original
884-second crash.

A fresh base build of root `4736b81d` / SDK `636154e` also passed the checked
two-cycle route (session `20261018T140936Z-p8620`). All 38 emitted allocation
trace events selected object `0x834B49F8` and target `0x82E5B7C8`. The object
maps to v4 through a paired data reference, and the target function matches
exactly. The route did not reproduce the fault. The trace records call
arguments, not allocation results, and does not establish which allocator
the reporter selected. Four traced requests used size `0x00697828` and
attributes `0x208C800E`, matching the original snapshot's saved allocation
arguments (`r27`/`r28`), without reproducing the fault.

The same fresh base build passed a 12-cycle extension in one process
(session `20261018T141520Z-p44580`): 12 speech loads/unloads, 13 media loads
and 12 unloads, with 128 emitted allocation events selecting that same pair.
The checked route now sends seven downward steps to QUIT: it includes the
optional HORIZON RALLY row and clamps at QUIT on the base seed without it.
The revised route passed again on the base seed. A single upward step from
MAP does not wrap to QUIT and was rejected during calibration.

The rebuilt base Android APK completed the two-cycle route on the Odin
(session `20261018T144326Z-p25658`), using a private copy of the pinned base
seed: five LANGUAGE changes, 11 captures, a normal completion, two speech
unloads and two media unloads, with no memory fault. Its log also contains a
nonfatal `PM4_DRAW_INDX_2` backend draw failure, so this is lifetime coverage,
not a clean renderer qualification. The original installed APK was restored
and its hash checked; all 17 player user-file hashes were unchanged. The
qualification state and temporary probe files were removed. This does not
replace the outstanding Pixel 3 XL / Linux 4.9.337 validation.

The revised route passed the full Windows v4 render-test checks from pinned
seed `i443-camera-v4` (session `20261018T144607Z-p3328`): five LANGUAGE
changes, two speech loads/unloads, three media loads and two unloads. All 38
emitted allocation events selected v4 object `0x835AA444` and target
`0x82F1D3F0`, confirming that mapping live. The base rerun of the revised
route also passed (`20261018T144330Z-p45580`).

The first v4 run to reach both transitions was rejected by the runner for
`ExecutePacketType3 overflow` and an indirect-ringbuffer execution failure.
A fresh rerun after compilation finished passed every check. These renderer
observations, including the Odin draw failure, remain separate follow-up
work; no renderer change was made in this batch.
