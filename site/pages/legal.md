---
title: Legal
section: Project
order: 1
description: What Pinyon Shift distributes, what you must supply, and the licence of the project's own code.
---

# Legal

Pinyon Shift distributes independently written source, build configuration, patches and its launcher. Releases don't include the game, extracted assets, executable modules, generated translations or a linked game binary.

## What you supply

A lawfully acquired, personally dumped copy of the exact supported disc. The build reads and verifies it on your machine. Nothing uploads, shares, modifies or helps locate game content, and verification can't be bypassed.

## Don't redistribute

- Disc images, executable modules, title updates, keys or extracted assets.
- Generated translation source or object files derived from the game's executables.
- Built game executables, Android packages or support files that contain game data.

The Android package you build holds the game translated from your disc. Keep it on your own devices.

## Native code that replaces the game's

Some of the game's translated code runs as native code instead: hand-written functions, hooks, native versions of whole subsystems, and replacements of libraries linked into the game such as FMOD Ex. That code is written from our own analysis of what the original takes, returns and changes, and checked against the translated original. A clean-room version may compute differently where the check allows it. The repository doesn't hold transcriptions of disassembly or decompiler output, which would copy the executable's expression, or data copied from the executable: tables the code needs are read from your own copy.

## Licence

The [BSD 3-Clause License](https://github.com/arcanite24/pinyon-shift/blob/dev/LICENSE) covers only the independently written material in the repository. It grants no rights to *Forza Horizon*, Xbox software, ReXGlue or anything you supply. Third-party components are listed in [THIRD_PARTY_NOTICES.md](https://github.com/arcanite24/pinyon-shift/blob/dev/THIRD_PARTY_NOTICES.md).

Microsoft, Xbox, Turn 10 Studios, Playground Games and *Forza Horizon* are the property of their owners. Pinyon Shift isn't affiliated with or endorsed by them.

This page describes the project's distribution policy and isn't legal advice. The source of record is [docs/LEGAL.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/LEGAL.md).
