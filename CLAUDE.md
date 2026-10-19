# Repository agent instructions

## Commit messages

Use Conventional Commits for every commit subject:

```text
<type>(optional-scope): <imperative summary>
```

- Use one of `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`,
  or `chore` as the lowercase type.
- Keep the summary lowercase, imperative, free of a trailing period, and no
  longer than 72 characters including the type and optional scope.
- Keep each commit focused on one logical change. Use a scope only when it
  makes the affected subsystem clearer, such as `fix(rexglue): ...`.
- Add a body after a blank line when the reason or behavior is not obvious.
  Explain why the change is needed and wrap body text at 72 characters.
- End the body with `Tests: <commands or result>` when validation was run.
- Mark breaking changes with `!` before the colon and add a
  `BREAKING CHANGE: <description>` footer.
- Never credit an AI assistant: no `Co-Authored-By` trailer, "Generated
  with" line or other assistant attribution in commit messages, pull
  requests or release notes. Commits are authored by the maintainer only.

Examples:

```text
fix(rexglue): match Xenon vmsum overflow behavior
ci: update ReXGlue patch release contract
docs: record AppData save launch procedure
```

## Keep the docs site current

The site in `site/pages/` is published from `dev` on every push
(`.github/workflows/pages.yml`), so it must describe what `dev` does.
Update it in the same change, or in a `docs(site): ...` commit pushed
together with it, whenever work:

- changes how the recompiler, runtime, renderer or a platform port
  works, or changes a measured number a page quotes;
- keeps or rejects an optimization or technique after measuring it
  (kept results go on the matching Internals page, rejected ones in
  the "What didn't pay off here" table in `lessons.md`, so they are not
  retried without a new reason);
- finds a method or lesson that other Xbox 360 recompilation projects
  could reuse (`lessons.md`);
- adds or changes something players see: a setting, a feature, an
  install, build or troubleshooting step (the player pages and
  `site/features.toml`).

Before finishing, search `site/pages` for statements the change makes
wrong (for example `rg -n "LTO|locals" site/pages`) and fix them.

Write for the reader, not the change log:

- Say what the thing does, why, and what it measured, with the device
  and method. No marketing language.
- Link to `docs/` for detail instead of copying it.
- Write only our own analysis: no disassembly, decompiled code or game
  data (docs/LEGAL.md).

Build the site with `.local/site-venv/Scripts/python site/build.py`
and check that new links and anchors resolve in `site/_build`.

## Launching with the AppData save

When an AppData-backed gameplay run is needed, launch the locally built preview
through `tools/launch-preview.ps1` and pass the installed preview state directory
as `-StateRoot`. This is the reference save on multivac: every discount sign
found, all 21 DLC packages installed, the v4 title update installed and on
(offline 1000 Club too). Launch it with the v4 build (`tools/build-v4.ps1
-StateRoot $stateRoot` first when the code changed):

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
.\tools\launch-preview.ps1 -StateRoot $stateRoot -TitleUpdateV4
```

The first v4 launch makes the profile v4-only; launch-preview backs up the
base profile to `$stateRoot\backups\pre-v4` before it. Older player saves
from other folders are archived in `D:\pinyon-save-archive`.

Before launching, verify that `$stateRoot\user` contains a
`ForzaProfile\ForzaProfile` file and that no `pinyon_shift` process is already
running. Do not use `%LOCALAPPDATA%\PinyonShift` itself as the state root for
this save; that top-level directory contains a separate user tree that the
active installed preview does not use.

If the installed version changes, locate the newest matching
`%LOCALAPPDATA%\PinyonShift\source\*\.local\preview\user\**\ForzaProfile\ForzaProfile`
and pass its enclosing `.local\preview` directory as `-StateRoot`. Never move,
delete, reset, or overwrite the AppData save.

## Scripted render tests from a pinned seed

Scripted routes must not depend on how far the live save has progressed. Take
a read-only snapshot of the AppData save with `tools/create-render-seed.py`
(it copies `user`, `config` and the FH1 shader catalogs into
`.local/render-seeds/<name>` and refuses to overwrite an existing seed), then
run routes through `tools/run-fh1-render-test.py` with that seed as
`--state-root`. The runner copies the seed into a private per-run directory,
so neither the seed nor the AppData save is ever written.

## Record reverse-engineering findings

Whenever work identifies something about the game by reverse engineering
(a guest function's purpose, a global, a struct layout or field offset, a
vtable, a file format, a cvar's effect on guest code, or a base-to-v4
address mapping), write it down in the same change, before moving on:

- Name it in the repository's records, not only in a code comment or a
  commit message: semantic symbols and offsets mod code uses go in
  `config/mod/fh1-symbols.toml` (v4 offsets in
  `config/mod/fh1-offsets-v4.toml`); everything else gets a `[[finding]]`
  record in `site/findings/<topic>.toml`, under the group (page section)
  it belongs to. The docs site renders these on the Reverse engineering
  pages (`site/pages/game-*.md`) and in the address index; a new group
  needs a `{{findings:<topic>/<group>}}` line on its page, or the build
  fails. `docs/REVERSE_ENGINEERING.md` only points there now (issue #448).
- Record the base address (and v4 address when known), a short name, what
  it does, how it was established (hook, trace, xref, string, experiment)
  and a confidence: confirmed, probable or guess. Fill `source` with the
  doc, backlog item or code that holds the detail.
- Findings that explain a subsystem (a file format, a render pass, a save
  layout) also get prose, a diagram or example code on that topic's page,
  and the subsystem's doc or backlog keeps the detail, linked from the
  record.
- Before adding a record, search `site/findings` for the address or name:
  extend the existing record rather than adding a second one on another
  page.
- Negative results count too: record what an address or option was found
  not to do, so the next investigation does not repeat it.
- Write only our own analysis: no disassembly listings, decompiled code or
  game data (docs/LEGAL.md).

## Forks and the SDK submodule

The maintainer's fork is `jricks92/pinyon-shift` (remote `fork`), with
`jricks92/shiftglue-sdk` as the matching fork of the SDK. `main` tracks
`fork/main`; push feature branches to `fork`. Upstream (`origin`) is
`arcanite24/pinyon-shift`.

`.gitmodules` still points `thirdparty/shiftglue-sdk` at the upstream SDK, so
on a feature branch whose SDK commits exist only on the fork,
`git submodule update` fails. Recover inside `thirdparty/shiftglue-sdk`:

```sh
git remote add fork https://github.com/jricks92/shiftglue-sdk
git fetch fork
git checkout <the branch the superproject's commit expects>
```

Whenever a feature branch bumps the submodule, push the SDK branch to
`fork` in the same step as the superproject branch, or the fork's commit
points at an SDK commit nobody can fetch.
