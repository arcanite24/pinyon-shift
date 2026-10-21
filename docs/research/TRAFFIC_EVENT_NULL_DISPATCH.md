# Traffic/event null dispatch (#703, #715)

Both supplied 0.6.0 reports fault in the **base** executable: guest read zero,
LR `0x82FFD9C4`, `r30` the owner, `r29 = r30 + 128`, `r31 = 0`, and `r3 = 0`.
The read is at `0x82FFD9E0`, before the first child's virtual call. The LR
still names the preceding lock call; it is not the faulting instruction.
The list count loaded into `r11` is one. This is an audio-library child
container, not evidence that a traffic vehicle itself was freed incorrectly.

## Contract and lifetime

The constructor `sub_82FFD460` initializes a count of one at owner `+124`
and an empty first slot at `+128`. Teardown `sub_82FFCB20` visits nonempty
children, releases them and clears their slots without reducing that count.
Thus a counted empty slot is part of this object's lifetime, not sufficient
evidence of an allocation failure or stale nonzero pointer.

The method `sub_82FFD980` takes the owner in r3 and a forwarded argument in
r4, locks the system's child-list mutex, visits count entries from `+128`,
and calls each child's vtable slot `+48`. It returns the last visited child's
result, or zero when none was visited, and unlocks on its normal exit.

The corresponding v4 method `sub_830BEAF8` already checks for an empty slot
and continues without changing the last result. Pairing is established by
the same `+48` slot in the corresponding vtables `0x8227E680` and
`0x822918A0`, the surrounding methods, and the matching lock/loop/unlock
contract. The added branch explains why a whole-function byte-shape match
does not find it. Constructor and teardown equivalents are `0x830BE5D8`
and `0x830BDC68` (same vtable family; constructor verified separately).

## Base correction

`PinyonShiftGuardEmptyAudioChild` runs before the base's null dereference.
For zero only it supplies the previous result to the existing loop tail,
which advances the index, reloads the count and reaches the normal unlock.
Live children follow the original call. Nonzero invalid pointers still
fault; zero-page protection stays enabled. No count, slot, lock or ownership
state is rewritten. Up to 16 `audio.child_dispatch.empty` events identify
the owner, index and preserved result without reading guest memory again.

The v4 hook is after its native null branch, so v4 retains its existing
empty-slot behavior. Its mapped continuation is the loop tail after the
result assignment, because v4's loop uses different index/slot registers.

## Evidence and acceptance

- #703: Windows 11, Ryzen 3600, RTX 2070 Super, XE and DLC; failing session
  `20261018T164536Z-p10768`, fault at 19:19:19.393. Five later sessions have
  normal shutdown markers (p25572, p2532, p20100, p25560, p24440). Those are
  separate runs and do not establish recovery from the failing session.
- #715: Omarchy 7.2.8-9-omarchy, RX 7600 / RADV `109060101`, 2x, 3436 s,
  SDK `79d3e6f`, exit -11. The ZIP's final guest fault matches #703. The
  screenshot is Clifton Valley's Noble M600 speed stunt, East Rt. 20 speed
  trap (173 mph, 1:30). Its mod state is not established by the report.
- Raw logs, the Linux ZIP and the screenshot remain in the read-only fleet
  triage attachments. Do not infer an OS or GPU cause from the signal.

Run `fh1-traffic-event-dispatch` with a 60 fps output limit from private stock
base, XE base and stock v4 seeds. XE's manifest targets the base executable
(`tools/pinyon_xe.py`); forced XE/v4 is outside that supported matrix.
The route covers traffic observation,
event entry, movement, retirement and reloading; screenshots and events must
establish that those transitions really occurred. A successful route alone
does not establish the reporter's disappearing-car symptom or a race finish.
The compiled hook test covers empty/live/mixed children and preservation of
the last result without requiring a timing-dependent live null slot.

Keep the parked fixture at the event marker with the handbrake. The initial
native v4 route rolled beyond sign-up before X and timed out waiting for car
selection (still mode 17); this was not a guest fault. A service-brake hold
instead drove the automatic car backwards. The route holds A (handbrake)
after the last startup press until sign-up, leaving traffic enabled.

Validation on multivac and the reference Steam Deck LCD, 2026-10-18:

- Private SDK `7ae0b57` generator; base and v4 regeneration pass their
  respective three-warning allowlists. Windows Release base/v4 and Linux
  x86-64-v3 base/v4 builds pass (Linux compiles the frozen private output).
- `python -m pytest tools`: 591 passed, 5 skipped. The compiled hook tests
  cover zero/live pointers and preserved results. A private harness compiled
  the actual generated methods with controlled memory under Windows and
  Linux Clang 20.1.8: original base faults on a zero slot; corrected base and
  native v4 pass empty, live, mixed and invalid-nonzero-pointer cases, with
  the expected call, result and unlock counts.
- Windows and native SteamOS each pass stock base, XE 1.01 base and stock v4
  event routes: 13 captures each, modes 17 -> 3 -> 17 -> 0 -> 17, movement,
  retirement and reload. Vulkan 1x, 1280x720, 60 output fps limit; these are
  functional tests, not performance measurements. Windows uses the
  launcher's bundled Immersive Camera 1.2.0 in all three cases; Linux has no
  extra mods in stock and XE alone in the XE case. Forced XE/v4 is excluded.
- Existing `fh1-hitch-drive` also passes on Windows stock and XE base at the
  default unlocked output rate, using its 60 Hz logical input clock.
- No base run emitted `audio.child_dispatch.empty`. These short routes do
  not reproduce the supplied failing session; the nil-state proof remains
  the generated-method comparison, not a claim that the reporter's traffic
  disappearance has been reproduced or fixed.
- All three original seed profile hashes and 17 normal Deck binary, config
  and profile hashes remain unchanged. Runs use private copies of seeds;
  the normal Steam entry, build and settings are untouched.

Reporter acceptance still needs the original road/stunt and mod version,
or a private reproducing seed if the pinned fixtures do not trigger it.
Keep stock/XE and base/v4 results separate, test Windows and native Linux,
and complete a race and save/reload before closing either issue.
