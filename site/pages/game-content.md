---
title: Cars, events and DLC
section: Reverse engineering
order: 13
description: How Forza Horizon defines its content: the gamedb.slt database and its tables for cars, upgrades, liveries and events; free-roam activities and event restrictions; how downloadable content is mounted, merged and licensed; the Rally expansion; and what title update 4 adds.
---

# Cars, events and DLC

Forza Horizon's content is mostly **rows in one SQLite database**, `media/db/gamedb.slt`, with 221 tables. A car is rows in about 47 of them; an event is rows in `Events`, `Races`, `Tracks` and their participant and reward tables. Names in the database are string-table references (`_&N`), resolved through the `.str` tables ([Files and formats](game-files.md#string-tables)). The models, textures and physics XML a row points to live in per-car archives under `media/cars/`.

Downloadable content extends the same database. Each package mounts as `DLCRoot<n>` and brings its own merge database, which the game merges into the base one shortly after Start, plus its archives; licence masks decide what the player may use. The Horizon Rally expansion is a package like the others, but its game code is only in title update 4.

The community [UDLC pack](dlc.md#community-udlc) follows that content layout:
a `.puboffer`, a merge database with 113 car rows, and localized car and make
string tables. Its rows already mark the cars installed and purchased; the
importer preserves the package's zero licence mask. This inspection describes
how it registers content, with qualification recorded in the
[DLC backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DLC_BACKLOG.md#community-udlc-595).

The database is the fastest way to answer "where is X defined". Open it read-only with any SQLite tool; for example, each event's races and their track ids:

```sql
-- sqlite3 "file:media/db/gamedb.slt?mode=ro"
select e.Id, e.CareerTypeId, count(r.Id) as races, group_concat(r.TrackId) as tracks
from Events e
join Races r on r.EventId = e.Id
group by e.Id
order by e.EventOrder;
```

and a car with its make:

```sql
select c.Id, c.Year, c.MediaName, c.ClassID, m.ManufacturerCode
from Data_Car c join List_CarMake m on m.ID = c.MakeID
order by c.Year;
```

`MediaName` names the car's archive, `media/cars/<MediaName>.zip`, for all 176 base cars. `tools/manage-fh1-dlc.py` imports and enables a player's own DLC packages ([DLC](dlc.md)).

## Game database

{{findings:content/Game database}}

## Cars

{{findings:content/Cars}}

## Upgrades, colours and liveries

{{findings:content/Upgrades, colours and liveries}}

## Events and career

Career events are database rows; free-roam activities (speed cameras, average speed zones, stunts, shops and barn finds) are flow documents in `gamemodes.zip` ([Game flow](game-flow.md)), placed in the world by trigger zones. Their run-time objects are on [Game objects](game-objects.md#activities-and-collectibles).

{{findings:content/Events and career}}

## Event restrictions

Which cars an event accepts comes from two places: its `EventRestrictions` row, a hex string decoded into per-bucket limits (make, model year and others), and its `Events.TargetClass`, applied on top. The developer options that sound like they lift restrictions are read nowhere ([Systems and leftovers](game-systems.md#launch-options)); the trainer's ANY CAR IN ANY EVENT hooks the row parser and the class step instead.

{{findings:content/Event restrictions}}

## Downloadable content

{{findings:content/Downloadable content}}

## Entitlements and licences

{{findings:content/Entitlements and licences}}

## Rally expansion

{{findings:content/Rally expansion}}

## Title update content

{{findings:content/Title update content}}
