# Vehicle player/traffic semantic ingress

Status: implemented as a default-off, read-only C4 census. Static retail
identity is proved. Two AppData qualifications found the exact local player,
closed its direct entity/ID joins negatively, and selected the exact owning
vehicle-map pool as the final bounded parent-lineage check.

## Exact retail contract

Retail RTTI exposes five related map-entity classes with independent primary
vtables: `CMapEntityVehicleBase` (`8201D338`),
`CMapEntityVehiclePlayerLocal` (`8201D380`), `CMapEntityVehicleAI`
(`8201D3C8`), `CMapEntityVehicleFestivalTraffic` (`8201D430`), and
`CMapEntityVehicleRemotePlayer` (`8201D4B0`). All have 13 virtual slots. The
local-player, AI, traffic, and base tables share every target; the remote-player
table differs only in its deleting destructor. The dynamic primary vtable is
therefore the exact class discriminator.

Two shared virtual methods establish the bounded object fields:

- slot 11, `82BBA010`, returns the 32-bit vehicle ID at receiver offset 12;
- slot 3, `82BBA1B8`, returns the pointer at receiver offset 16.

The offset-16 values are title-owned class names immediately following their
respective vtables: `vehicle_type`, `player_local`, `ai`, `traffic`, and
`player_remote`. The base constructor `82558510` stores that pointer at offset
16, while `82CCF228` assigns the vehicle ID at offset 12. AI constructor
`82558698` independently proves the type-name and vtable installation pattern.

The local-player creation edge is also exact. Constructor `82558620` calls the
vehicle base constructor with type-name pointer `8201D3B4`, then installs the
`8201D380` player-local vtable. Pool constructor `8255B238` embeds that object
at pool offset 32, followed by six 64-byte AI objects beginning at offset 144.
Initializer `82629088` allocates the 1,792-byte pool, passes root offset 4 as
the pool's offset-16 context, and stores the completed pool at root offset 24.

`discover-native-renderer-vehicle-player-ingress.py` locks the five RTTI
descriptors, complete-object locators, vtables, all 13 targets, class-name
pointers, and the getter/setter/constructor instruction contracts. It does not
infer a player label from an address or render hash.

## Runtime join

A passive hook at the exact ID getter observes its already-live receiver. The
host admits only the five statically locked primary vtables, then records the
entity address, ID, and exact class-name pointer in a fixed 128-entry table.
Unrecognized receivers remain separately accounted because the tiny getter can
also be used with transient compatible objects.

Every admitted entity is compared only with the existing exact vehicle-pose
tuple at `82BC5A3C`. Nine exact relationships are retained independently in a
fixed 256-entry table:

- map entity address equals pose source;
- map entity address equals pose owner; and
- map vehicle ID equals pose active slot;
- vehicle-map pool equals pose source or owner;
- pool-owning root equals pose source or owner; and
- pool context (`root+4`) equals pose source or owner.

Each correlation retains the complete pose identity, relation, frame span, and
observation count. This avoids repeating the rejected broad object scans and
allows the offline qualifier to determine whether one relationship uniquely
and stably selects a player-owned pose.

## Safety and next gate

The census reads only the receiver's main vtable, ID, and class-name pointer.
It does not read a class-name payload at runtime, scan any object, export guest
constants or assets, issue a native draw, publish a target, or suppress Xenos.
Address-table overflow, type-name mismatch, identity drift, or an ambiguous
player-to-pose relationship fails closed.

The first 2026-08-31 AppData session observed 2,035,902 getter calls, including
48,918 calls on the five locked vehicle classes and 3,156 calls on exactly one
stable `player_local` object (`4066DB00`). All 23 admitted objects retained the
unassigned ID sentinel `FFFFFFFF`; the player therefore made zero eligible
pose comparisons because the first observer incorrectly gated all direct
pointer comparisons on an assigned ID.

The corrected Xenos-authoritative session then made 19,907 direct comparisons
for the one exact `player_local` entity with zero entity/source or entity/owner
matches. The setter had zero calls, confirming that this fixed descriptor pool
does not receive live numeric IDs through the class API. A proposed creation
edge was also rejected by runtime and corrected statically: `828FA310` installs
`8207D380`, not `8201D380`. This is why high- and low-half address formation is
now part of the locked constructor proof.

The last bounded parent edge observes the exact pool installation at
`826291A8`, derives the already-constructed player entity as pool plus 32, and
retains only pool, root, and root-context addresses. The next batched AppData
session tests their six direct source/owner relationships. A zero-hit or
ambiguous result closes this descriptor-pool branch; it must not trigger
another broad object scan.

Only a proved relationship may label the already-qualified 30-family semantic
constant bridge as the player vehicle. Mesh/material contribution labels and
native admission remain separate gates. The qualification launch accidentally
inherited the restart-gated `comparison_native` display selector; that affected
only displayed diagnostic authority. Telemetry confirms the census changed no
guest state, and future identity runs use Xenos output unless comparison is
explicitly requested.
