---
title: Game objects
section: Reverse engineering
order: 6
description: The object graph a mod walks in Forza Horizon: the game holder and its world, the session's game mode, the time-of-day object, the player car and cameras, the activity manager with its discount signs and barn finds, map markers and the career profile, with a mod that reads them.
---

# Game objects

Nearly everything a mod reads in the running game is reached from one global, the **game holder** at `0x832DF024` (v4 `0x833CAAE4`). From it a few pointer loads lead to the world, the user and the component list; from those, to the game mode, the clock, the free-roam activities and the career profile. The offsets below are stable enough that the [mod API](modding.md) names them, so a mod asks `find_offset("time_of_day.seconds")` rather than hard-coding 10488.

{{diagram:game-objects|The paths from the game holder to the objects mods use. Offsets are in bytes; every arrow is a 32-bit pointer load. Only the profile's loaded flag moves in v4.}}

This mod logs the game mode, the clock and how many free-roam activities are revealed every 300 frames. It only reads, so it can run from the frame tick without a guest task:

```c
#include "pinyon_mod.h"
#include <stdio.h>
#include <string.h>

/* Base-game globals; v4 moves them to 0x833CAAE4 and 0x833EDA1C. */
#define GAME_HOLDER 0x832DF024u
#define ACTIVITY_MANAGER_INDEX 0x832FEE8Cu

static const PinyonModApi* api;
static unsigned frames;

static uint32_t load_u32(uint32_t address) {  /* guest memory is big-endian */
  uint8_t b[4] = {0};
  if (!address || api->read_guest(address, b, 4)) return 0;
  return (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3];
}

static uint8_t load_u8(uint32_t address) {
  uint8_t value = 0;
  if (address) api->read_guest(address, &value, 1);
  return value;
}

static float load_f32(uint32_t address) {
  uint32_t bits = load_u32(address);
  float value;
  memcpy(&value, &bits, sizeof value);
  return value;
}

static uint32_t field(const char* name) { return (uint32_t)api->find_offset(name); }

static void report(void) {
  uint32_t handle = load_u32(load_u32(GAME_HOLDER) + 4);
  uint32_t world = load_u32(handle + 4);
  if (!handle || !world) return;

  /* Game mode and time of day hang off the world. */
  uint32_t mode = load_u32(load_u32(world + field("world.session")) + field("session.game_mode"));
  uint32_t clock = load_u32(world + field("world.time_of_day"));
  float seconds = load_f32(clock + field("time_of_day.seconds"));

  /* The activity manager is one entry of the component array. */
  uint32_t array = load_u32(load_u32(handle + field("game.components")));
  uint32_t index = load_u32(ACTIVITY_MANAGER_INDEX);
  uint32_t manager = array && index < 4096 ? load_u32(array + 4 * index) : 0;
  uint32_t begin = load_u32(manager + field("activity_manager.begin"));
  uint32_t end = load_u32(manager + field("activity_manager.end"));
  unsigned total = 0, revealed = 0;
  for (uint32_t slot = begin; manager && slot < end && total < 4096; slot += 4, ++total) {
    revealed += load_u8(load_u32(slot) + field("activity.revealed")) != 0;
  }

  char text[128];
  snprintf(text, sizeof text, "mode %u, %02d:%02d, %u of %u activities revealed", mode,
           (int)(seconds / 3600) % 24, (int)(seconds / 60) % 60, revealed, total);
  api->log(PINYON_LOG_INFO, text);
}

static void on_frame(void* user, const PinyonHookEvent* event) {
  (void)user;
  (void)event;
  if (++frames % 300 == 0) report();  /* FRAME_TICK runs on the main thread */
}

PINYON_MOD_EXPORT uint32_t rex_mod_abi_version(void) { return PINYON_MOD_ABI_VERSION; }
PINYON_MOD_EXPORT int rex_mod_create(const PinyonModApi* host, PinyonMod* mod) {
  api = host;
  api->subscribe(PINYON_HOOK_FRAME_TICK, on_frame, NULL);
  mod->self = NULL;
  return 0;
}
```

The two globals are written as base-game addresses because the symbol table names only functions, hook sites and offsets; the comment gives their v4 addresses. Calling guest functions instead (`world.game_mode`, `profile.credits`, `activities.reveal_all`) needs a guest task; [Methods and tools](game-methods.md#probe-mods) shows one. The full list of named functions and offsets is on [Address index](game-addresses.md#mod-symbols).

## Game and world

{{findings:objects/Game and world}}

## Session and game mode

{{findings:objects/Session and game mode}}

## Audio child dispatch

A counted child list can contain empty slots during construction and teardown.
The base audio dispatch now skips those slots as v4 already does, preserving
the previous result and the normal unlock. This addresses the null read seen
in the traffic/event reports; the vehicle disappearance and the transition
that exposes the empty slot still need route qualification. The
[investigation](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/research/TRAFFIC_EVENT_NULL_DISPATCH.md) records the
Windows/Linux evidence and the separate stock/XE acceptance requirements.

{{findings:objects/Audio child dispatch}}

## Time of day

{{findings:objects/Time of day}}

## Vehicles, camera and crowd

{{findings:objects/Vehicles, camera and crowd}}

## Car dynamics

The player's car keeps its physics behind an `ICarDynamics` interface. The game's own dashboard and rumble read the engine, gear, speed, ABS and per-wheel slip from it, and so do the DualSense trigger effects (see [Playing](playing.md#dualsense)). A reader goes from the world to the player's car slot, then to the car, then to the interface:

```text
world    = [[[0x832DF024] + 4] + 4]
car      = [sub_8248BAE8(world)]          player car slot -> car
dynamics = [car + 11664]                  ICarDynamics
wheel w  = dynamics + 3936 + 1024 * w     0, 1 front; 2, 3 rear
```

{{findings:objects/Car dynamics}}

## Activities and collectibles

Free roam's collectibles and points of interest are **activities**: discount signs (`CActivityFlyers`), barn finds, speed cameras, average speed zones, gas stations and the rest. Discount signs and barn finds also keep a saved record in the profile, which is how the game remembers what was found and revealed.

{{findings:objects/Activities and collectibles}}

## Profile

{{findings:objects/Profile}}

## Lifetime and containers

Small helpers that turn up in many call stacks: reference counting, handles and container growth. Knowing them saves time when reading a crash or a profile.

{{findings:objects/Lifetime and containers}}
