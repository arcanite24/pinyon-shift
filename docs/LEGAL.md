# Legal and distribution

Pinyon Shift distributes independently authored source, build configuration,
patches, and its launcher. Releases do not distribute the original game,
extracted assets, executable modules, generated translations, or a linked game
binary.

Users must supply a lawfully acquired, personally dumped copy of the exact
supported disc. The build workflow verifies and reads that image locally. It
does not upload, share, modify, bypass verification for, or help locate game
content.

Do not commit or redistribute:

- disc images, executable modules, title updates, keys, or extracted assets;
- generated translation source or object files derived from game executable
  modules; or
- locally linked preview executables or support files containing game data.

## Native replacements of game and library code

Pinyon Shift replaces some of the title's translated code with native code:
`src/guest_native`, hooks, and replacements of the libraries linked into
the game (XDK libraries and middleware such as FMOD Ex). The repository may
hold a replacement only when it is independently authored:

- It implements a contract documented from our own analysis: what the
  function takes, returns and changes in guest state, recorded in
  `site/findings`, and checked by comparing its results with the translated
  original within a stated tolerance.
- Its algorithm is our own or comes from a published source under a
  compatible licence: standard signal-processing filters, codecs, maths, or an
  open-source library listed in `THIRD_PARTY_NOTICES.md`.

The repository must not hold:

- a game or library function rewritten statement by statement from its
  instructions, its disassembly or a decompiler's output. Such a hand
  translation is derived from the executable like the generated source above;
- constant tables, coefficients or other data copied from the executable. A
  replacement that needs them reads them from the player's own files at
  build or run time;
- a middleware product's own algorithms reproduced beyond what its public
  documentation and the published literature define. Middleware is
  replaced at its documented API boundary.

When a replacement must keep the original's exact arithmetic, it is produced
at build time from the player's own executable, for example by a
code-generator option or a specialised translation of that function. It
then stays in the generated tree, which is never committed.

## Upscaler and frame generation runtimes

Vendor upscalers and frame generators (DLSS, FSR, XeSS, Lossless Scaling)
are planned in [UPSCALING_BACKLOG.md](UPSCALING_BACKLOG.md). Their
licences were read on 2026-10-16 (UP-0.1). The policy:

- **No vendor binary, header or shader is committed, and no release ships
  one.** Releases stay source and launcher only; the player's setup fetches
  what the build needs.
- **Open-source code is fetched at setup and built locally**, like the other
  setup downloads in `THIRD_PARTY_NOTICES.md`: FSR 1-3 and the FidelityFX
  SDK 1.1.x source (MIT), NVIDIA Image Scaling (MIT), Arm ASR (MIT) and
  Snapdragon GSR (BSD-3).
- **Redistributable vendor binaries are fetched from the vendor at setup**,
  pinned by version and hash, with their notice kept: the signed FidelityFX
  DLLs (AMD's licence allows binary redistribution with the notice; no
  reverse engineering) and XeSS (Intel Simplified Software License:
  unmodified binaries with the notice; no reverse engineering, no use of
  Intel's name to endorse). XeSS's public headers are MIT since 2026-09.
- **DLSS (the NVIDIA RTX SDK licence) ships with the Windows build, with
  NVIDIA's approval (2026-10-20).** That licence lets an application
  distribute the SDK only as object code inside it, on terms at least as
  protective as NVIDIA's. It forbids using the SDK in a way that subjects it
  to an open-source licence (§4(e)), and it asks for attribution with
  NVIDIA's marks on the splash screen, about box and credits of an
  application that incorporates DLSS or NGX. So the DLSS SDK is still never
  committed: the player's setup downloads the NGX headers, the static
  loader and `nvngx_dlss.dll` from the pinned `github.com/NVIDIA/DLSS`
  commit, checked by SHA-256 (`thirdparty/shiftglue-sdk/cmake/rexglue_dlss.cmake`),
  links the loader into the player's own build and stages the DLL with
  NVIDIA's `LICENSE.txt` in `upscalers/dlss/<version>/`. The launcher
  names it "NVIDIA DLSS" and `THIRD_PARTY_NOTICES.md` attributes it. The
  game also loads `nvngx_dlss*.dll` from a newer version folder the player
  adds there (NGX's documented `PathListInfo` search path). Contact for
  licence questions: `nvidia-rtx-license-questions@nvidia.com`.
- **`Lossless.dll` is never downloaded, copied or redistributed** by the
  project. Lossless Scaling is a paid Steam application. Its frame
  generation may be used in two ways only:
  - The player runs the application over the game window. This needs
    nothing from us.
  - After THS (the developer) gives permission, the game loads the DLL
    from the player's own Steam install at run time. Nothing extracted
    from it is stored outside the player's machine.

  No terms of use beyond Steam's were found. lsfg-vk, the Linux
  implementation that loads the same DLL, is CC BY-NC-ND since 2026-08, so
  its newer code is not reused.

Never vendor or link to leaked SDK builds (FSR 4 source, INT8 FSR 4), and
never document installs that turn off a vendor's signature checks.

The BSD 3-Clause License applies only to the independently authored material in
this repository. It grants no rights to *Forza Horizon*, Xbox software, ReXGlue,
or any user-supplied content. This document describes the project's distribution
policy and is not legal advice.
