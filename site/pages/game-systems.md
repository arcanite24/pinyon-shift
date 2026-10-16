---
title: Systems and leftovers
section: Reverse engineering
order: 14
description: Forza Horizon's developer launch options and how to set them, debug features left in the retail build, the online services the game still calls, leftover modes and hardware support, and gameplay systems such as game control, race statistics, rewind and AI rubber-banding.
---

# Systems and leftovers

The retail executable still contains much of the developers' tooling. About 300 **launch options** (`nohud`, `skiptutorials`, `numaicars`, `mainthread30fps` and others) are parsed into one options object, but the retail build never receives a command line, so none of them is set unless something writes the object directly. Debug menus, test tracks, telemetry pages, split-screen and linked-console code survive too; most of it cannot be reached.

The options object is a static singleton, so its flags are bytes at fixed addresses. A mod can set one, as long as it writes after the object is built and keeps writing. Each flag is read when the game needs it: `nohud`, for example, is read before a HUD element first shows, so it must be set from boot (Pinyon Shift's own HUD toggle uses a separate hidden byte instead, [UI, HUD and input](game-ui.md#hud-and-map)). This hides the HUD from the start:

```c
/* nohud: byte +3213 of the launch-options object at 0x832E29A0 (base game). */
static void on_frame(void* user, const PinyonHookEvent* event) {
  static const uint8_t on = 1;
  (void)user;
  (void)event;
  api->write_guest(0x832E29A0u + 3213, &on, 1);
}
```

Pinyon Shift sets three of these flags itself (the skippable voice-over, the idle intro replay and the automatic reset); the records below say which flags work, which are never read, and which were not tested. The game's online services are gone, and the records under [Online services](#online-services) show where it still checks for them, which matters for features such as the 1000 Club and the Treasure Map.

## Launch options

{{findings:systems/Launch options}}

## Debug and developer features

The gameplay replay manager records a main stream and an attached secondary
stream. Its loader also needs initialization for the event and cars; keeping
an in-memory stream pointer cannot restore this after a restart. A read-only
Windows probe now exposes the base-disc registry for research. Saved gameplay
replays and fixed-cadence video export remain unimplemented; the
[contract and acceptance gates](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/GAMEPLAY_REPLAYS.md)
separate this work from whole-session deterministic replay and GPU frame replay.

{{findings:systems/Debug and developer features}}

## Online services

{{findings:systems/Online services}}

## Leftover modes and hardware

{{findings:systems/Leftover modes and hardware}}

## Gameplay systems

Fast travel runs through a native state graph that coordinates game control,
traffic, audio, the car move, streaming and the camera. Its teleport action
finishes before the graph's streaming wait, so its active flag alone cannot
confirm a safe landing. The trainer's experimental map option retains that
graph and the title's travel locks; GPS requests use the position action on
the guest thread. [Travel destination contracts and qualification](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/research/TRAVEL_DESTINATIONS.md)
describe the base/v4 arguments and the remaining checks.

{{findings:systems/Gameplay systems}}

## AI opponents

Each event names an AI skill, temperament and rubber-band row per opponent difficulty in the game database. When a car spawns, the game copies those rows into a per-car AI config, and the AI's controller reads its distances and factors every update. An AI that gets far enough ahead of the player enters a rubber-band mode: it makes a mistake on purpose or, further ahead, has its torque cut. An AI far enough behind turns on catch-up, which sharpens its braking and cornering. After each race the game also moves the player's AI skill by how their times compared.

Pinyon Shift's **AI OPPONENTS** setting ([Playing](playing.md#ai-opponents)) rewrites the per-car config right after the spawn call fills it, so the same change works on the base game, the title update and every platform without touching the database. "The player" below is the best-placed human for the rubber band and catch-up and the worst-placed one for the torque boost (`sub_82B73600` and `sub_82B736A0` over the 8 human slots at `0x83338740`); in single player both are the player (probable). Gaps are track distance in metres (`sub_82B73498`), positive when the AI is ahead.

{{findings:systems/AI opponents}}

## Wheel force feedback

With a wheel that reports force feedback, the game does not rumble it through the controller call. It drives the wheel through the kernel's XInputdFF calls instead, as it drove the Microsoft Wireless Racing Wheel: it downloads five effects (inertia, friction, damper, a spring that stiffens with speed and a constant force), starts them, then updates the constant force every frame. The SDK answers those calls, and its raw wheel path (**F6 > CONTROLS > RACING WHEEL > SEPARATE DEVICES**, [Playing](playing.md#racing-wheels)) plays them on the wheel.

{{findings:systems/Wheel force feedback}}

## Data and tuning files

{{findings:systems/Data and tuning files}}

## Crash guards and helpers

The facade-transition investigation separates a thread-stack mapping fault
from an allocation-override crash after unload/reload. A return address alone
does not identify which object was freed. The transition route requires both
facades to load and unload twice and changes LANGUAGE through the host menu;
those choices are saved for restart. On Windows, run it with a 60 fps guest
output limit so its frame-paced startup presses reach the timed opening
movies and title menu. Evidence and remaining validation are in
[facade lifetime faults](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/FACADE_LIFETIME_FAULTS.md).

{{findings:systems/Crash guards and helpers}}
