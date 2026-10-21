# Travel and GPS destinations (#485)

The title's fast-travel action is part of a state graph, not a single safe
teleport call. Static tracing on the supported base and v4 executables finds:

| Purpose | Base | v4 | Contract |
| --- | --- | --- | --- |
| Map travel predicate | `0x827FB088` | `0x828AF468` | Map component in r3; returns the title's travel permission AND the map's destination eligibility byte at +440. |
| Title travel permission | `0x82613E28` | `0x826BAAC8` | Fast-travel manager in r3; retains the title's scripted locks. |
| Map predicate return hook | `0x827FB0E8` | `0x828AF4C8` | r30 map component, r31 title permission, r11 result before conversion to r3. Exact normalized function match. |
| Map input-consumption hook | `0x82803344` | `0x828B787C` | Before the travel input test: r21 hovered marker, r31 map component. Arm a prepared request here and clear r21 for the native road fallback instead of a marker's transform. |
| Map predicate result hook | `0x82803360` | `0x828B7898` | The map update's own predicate result in r3, before conversion; r21 and r31 as above. Clears r21 only when the trainer override alone admitted the travel. The predicate also runs for the map's button hints, so the gate cannot clear r21 itself. |
| Native road lookup | `0x827FADE8` | `0x828AF1B8` | r4 pointer to float4 world position; r3 input unused; returns the closest road graph point. Base queries `road_type` through component index `0x832FF094`; v4 queries its GPS position manager at index `0x833EDC44`. |
| Teleport action enter | `0x829887E0` | `0x82A3C6D8` | `CTeleportCarToFastTravelDestination`; uses the manager's destination matrix and initializes per-instance progress. |
| Teleport action update | `0x82988948` | `0x82A3C848` | Advances per-instance progress and signals its completion transition. |
| Teleport action exit | `0x82981CD0` | `0x82A35888` | Clears the manager's active byte and resets the destination. |
| Current component list | `0x825F6FB0` | `0x8269B4F8` | No arguments; returns the current component-list header in r3. |
| GPS position action | `0x829423B0` | `0x829F5278` | r3 points to a 48-byte, 16-byte-aligned descriptor: +28 component-list header, +32 big-endian float4 (x,y,z,0). r4/r5 are unused. |

The fast-travel manager's component index is at base `0x832FF06C`.
Its byte +16 enables travel, +32 is the 64-byte destination matrix, +96
the map's quoted cost and +100 the teleport action's active flag. The map
component holds its nearest road graph point at +564 (v4 +576); that point's
world x/y/z are floats at +4/+8/+12. These fields were followed from the map
update to the matrix setter and the teleport action. They are not car pose
fields.

The native graph acquires game control, shows a loading screen, disables car
control and traffic spawning, performs the move, waits for streaming, restores
traffic, plays its camera sequence and releases game control. The action's
active flag clears before the later streaming wait: it cannot certify a safe
landing. Calling the move helper alone bypasses this sequence.

The trainer's map option changes only destination eligibility, with a readable
finite road point, free-roam mode 17 and the title's travel permission still
required. The map retains its normal selection, confirmation, cost and graph
entry. This also differs from the v4 profile entitlement: the cheat is temporary
and requires the isolated profile. No profile ownership field is edited here.

An explicit trainer destination is resolved through the map's own road lookup
in a queued guest task. It retains the road point only against that world's
component-list identity, expires after ten elapsed seconds and is cancelled if
cheats turn off, free roam ends or the world changes. A hook in the native map
update arms the travel-input byte (+426) immediately before its consumption
and selects the road fallback instead of a hovered marker. The title's
predicate still checks travel permission before the host clears the unrelated
cursor marker's quoted cost (+444). The native update clears its input latch
on exit; a cancelled request leaves no deferred input in an inactive map.

With FAST TRAVEL ANYWHERE on and no queued request, the hovered marker
decides the landing. After the map update's predicate passes, a nonzero r21
supplies its object's transform as the destination; a zero r21, or a marker
whose transform is the identity, leaves the nearest road point. An earlier
version cleared r21 on every physical travel press while the option was on.
On the v4 reference seed (2026-10-19) that moved a Horizon Outpost (South
Beaumont) landing from inside the outpost, in front of its entry, to the road
about 28 m away; with the option off the same press landed inside. Race
Central landed at the same pose either way. The trainer now clears r21 only
when the title refused the marker (its predicate result in r11 was false) and
the option admitted it: a barn find, which the title cannot travel to, lands
on its nearest road, and the outpost lands where the title puts it.

A queued request cannot repeat travel. The input hook writes the latch
immediately before the map update tests it, and the predicate it calls
reaches the gate in the same update, so the gate sees the latch it armed and
clears the request on the press that starts travel. If the map skips its test
that update, nothing travels and the next update re-arms. Three successive
v4 targets each logged one `waiting_for_map` and one `native_map_handoff` in
the same second, with no later travel or `cancelled` event.

Setting the latch only inside the predicate left an idle-map probe waiting
until a physical X press. A queued write outside the map update also expired
without moving the car. The input hook therefore sits at the consumption
point. Expiry uses elapsed time because the title-loop cadence is not the
route's 60 Hz presentation clock.
The native map then enters the same travel graph. Neither host thread writes
the car's pose. `native_map_handoff` records only that handoff, not streaming
completion. A request requires the full game map within its expiry interval. The trainer
pauses through the title's own pause menu: if that menu is on its MAP page,
A opens the full map and a later A confirms the travel dialog. A test that
counted the first A as confirmation stayed safely in the dialog.

The GPS action looks up the road-position manager through index
`0x832FF090`, resolves its position with `0x82CDC5A0` (v1 float4), then requests
the target on the sat-nav manager through index `0x832FF054` with
`0x8299FB40` (v4 `0x82A54068`). Its lock byte is +764 in both versions;
a locked destination rejects a request. With both managers present the action
returns the setter's low-byte acceptance. Its current-target getter
`0x82999820` (v4 `0x82A4DDA0`) returns the last pointer from the manager's
array at +52 and count +60, or zero when empty.
The host uses the existing action from a guest task, with fresh components
and temporary descriptor memory, rather than retaining guest object pointers
on the UI thread. Coordinates supplied by settings are bounded and finite.
The generic entry callback is a no-op in both executables (base `0x830B2320`,
v4 `0x82D9C8A8`), so the GPS execute path needs no constructed state instance.

## Base and v4 road orientation

The base map fallback derives its forward vector from a path attachment:
road +16 is the attachment count, +20 points to the first attachment, whose
+0 points to a path and +4 is the signed point index. A path has its point
count at +0 and point-pointer array at +4. The fallback chooses the previous
point when the index is positive, otherwise the next point when available;
without an adjacent point it uses the default +Z direction. A coincident or
vertical adjacent point cannot form a usable orthonormal car basis.

v4 changed this too: its map update (`0x828B6998`, corresponding to base
`0x82802580`) calls `0x82D9D070` and `0x82D9BA38` for a placement transform
instead of using the base attachment-direction calculation. Do not apply
base attachment offsets to v4 on the strength of the shared position layout.

A saved-point probe faced across the road on base and moved 3.97 m before
its driving wait, armed two seconds after throttle, began. The late wait
then timed out after the car stopped near traffic and roadside collision.
Checking the native adjacent-point calculation did not reproduce a degenerate
heading. The repeated route arms its movement wait immediately after throttle.
The title owns the final orientation; this feature does not rewrite its basis.

## Windows qualification (2026-10-18)

On multivac (Ryzen 7 5800X, RTX 4080, Windows x64), the native renderer at
1280 by 720 passed the twenty-target `fh1-teleport-streamed.fh1test` route
on private copies of the pinned base and v4 seeds. Each request entered the
native confirmation and streaming flow; the route then drove the car.

| Executable | Successive landings without a crash | Largest distance from resolved road point | Smallest post-landing drive |
| --- | ---: | ---: | ---: |
| Base | 20 | 5.300 m | 22.419 m |
| v4 | 20 | 5.300 m | 24.026 m |

All forty landing and forty driving captures were inspected: roads, terrain,
traffic and the supported car remained rendered, with ground contact and
player control after travel. The numeric check paired each handoff with its
own landing and driving captures, required mode 17, landing distance below
25 m, at least 3 m of subsequent driving and driving height within 15 m of
the resolved road. A handoff receipt alone was never counted as a landing.
The two executables need not return the same road point for the same input:
v4 uses a different native lookup implementation.

`fh1-custom-gps.fh1test` accepted the synthetic target (0,0,0) on both
executables. Both showed the resulting 4.7 km green map route, road guidance
arrows and HUD distance marker. Both rejected a later non-finite target.
The original seed profiles and their separate backups remain read-only;
the runner writes only its per-run state copies.

An earlier base pass missed one 100 ms map-button pulse during a hitch.
Its prepared request expired without moving the car; it was excluded from
landing counts. The qualification route holds map and confirmation buttons
for 500 ms and the repeated base pass completed all twenty requests.

Additional checks on both executables passed: the map's X travel action,
saving a selected map road in the trainer, GPS to that point after restart,
and teleport to it with subsequent driving. The restart route opened the
full map before requesting travel and confirmed the title dialog separately.

Closed-map requests expired after ten seconds without a car move or a late
handoff when the map was subsequently opened. A request prepared in car
selection cancelled four seconds into the transition to event mode 3,
before expiry; GPS requested in mode 3 was rejected. With cheats off, the
same destination settings produced no guest destination calls or car move.

## Remaining qualification

Other platforms are not qualified here. Exercise scripted free-roam missions
that own the GPS destination or disable travel before claiming coverage of
every mission-specific lock. The implementation retains the checked title
permission and sat-nav lock byte; it does not force either lock open.
