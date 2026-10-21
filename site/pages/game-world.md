---
title: World and tracks
section: Reverse engineering
order: 8
description: Forza Horizon's Colorado world: its track data and precomputed scenery visibility, why there is no draw-distance setting, what the car LOD tables do and do not control, placements, cameras, time of day and the absence of weather.
---

# World and tracks

The game ships one open world, Colorado, plus small UI "tracks" for the Autoshow, workshop and photo studios. Colorado's scenery is about 230,000 model files in one 2.9 GB archive (`media/tracks/colorado/bin.zip`), named through a filename map and made visible per **precomputed visibility zone** (PVS). What can be seen from where was baked when the track was built.

That answers the most asked question about this world: there is no draw distance to raise. The search for one ([#421](https://github.com/arcanite24/pinyon-shift/issues/421)) traced every distance-like setting the game reads, and each one either belongs to something else (the minimap, a car shader) or changed nothing visible when pushed to extremes. Those negative results are kept below so the search does not have to be repeated.

The track folder, with what each file is known to hold (unmarked names are not yet traced):

```text
media/tracks/colorado/
  bin.zip                    230,057 members: .bin, .bix models, .pgeo, .fiz
  TrackSettings.xml          grass, crowd, lightmap and depth-pass distances, tone map, wind
  SmashableObjectTypes.xml   object types the car may smash: Fence, Flyer, Mailbox, RaceActivation
  PVSZoneSpeeds.dat          per-zone data for the visibility system
  ColorGradingLookup.dds, ColorGradingLookup_Night.dds
  PhysicsDefinitions.bin, colorado.nav, colorado.owr, colorado.oww
  colorado_ambience.xml, colorado_reverb.xml, colorado_soundbank_lookup.xml
  Ribbon_00/
    FilenameMap_00.dat       model ids to member names in bin.zip
    Colorado_00.pvs          precomputed visibility zones
    PVSZLookup_00.dat        zone lookup
    CollObjs.xml             21,877 collidable placements: physics type, position, orientation
    GameObjs.xml             2,148 gameplay objects by GameplayID (barn finds and others)
    TrackRoute*.xml          243 routes: starts, waypoints, checkpoints, boundaries, finish
    TimeOfDay*.xml, PostProcessingZones_Safe.xml, ParticleEmitters.xml
    PreRaceCams.xml, TrackSegCams.xml, SmashableEffects.xml
    Colorado_00.hex, Colorado_track_00.col, Colorado_track_00.crowd
```

## Track data and scenery visibility

{{findings:world/Track data and scenery visibility}}

## Draw distance

`TrackSettings.xml` is plain XML the game reads in free roam; its distance fields work, but none of them extends what is drawn in the distance. The camera's far plane is a code default, and the `draw_distance` string belongs to the map screens.

{{findings:world/Draw distance}}

## Render scenarios and car level of detail

Car LOD distances live in the render scenarios ([Rendering](game-rendering.md#render-scenarios)). Hooks on every writer of these tables showed they are read, but scaling them by 0.01 did not change which car model is drawn: the visible LOD is chosen elsewhere, and where is not yet traced. The main-thread chain once suspected (see "scene draw on the render thread" above) is most likely the physics-world step.

{{findings:world/Render scenarios and car level of detail}}

## Collision and cameras

The chase camera starts from a `CameraSettings.ini` tuning block, then applies
per-car placement overrides. Live placement must adjust the instance's
cached offsets as well as the ground-height limits; changing only the
original INI-backed block does not update the cached placement. The
[camera editor](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md#camera-editor) retains
those loaded values so resetting preserves another mod's tuning too.

{{findings:world/Collision and cameras}}

## Placements and routes

`CollObjs.xml`, `GameObjs.xml` and the `TrackRoute*.xml` files in the ribbon folder place everything the player interacts with. They are plain XML. Free-roam activities are listed under [Cars, events and DLC](game-content.md#events-and-career); their objects, and the trackside crowd, under [Game objects](game-objects.md).

{{findings:world/Placements and routes}}

## Time and weather

The world has a full day cycle driven by one float, seconds since midnight. There is no weather: the only wet strings are tyre friction scales and the sky has one cloud set.

{{findings:world/Time and weather}}
