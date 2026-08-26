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

Examples:

```text
fix(rexglue): match Xenon vmsum overflow behavior
ci: update ReXGlue patch release contract
docs: record AppData save launch procedure
```

## Launching with the AppData save

When an AppData-backed gameplay run is needed, launch the locally built preview
through `tools/launch-preview.ps1` and pass the installed preview state directory
as `-StateRoot`. The current save is under:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
.\tools\launch-preview.ps1 -StateRoot $stateRoot
```

Before launching, verify that `$stateRoot\user` contains a
`ForzaProfile\ForzaProfile` file and that no `pinyon_shift` process is already
running. Do not use `%LOCALAPPDATA%\PinyonShift` itself as the state root for
this save; that top-level directory contains a separate user tree that the
active installed preview does not use.

If the installed version changes, locate the newest matching
`%LOCALAPPDATA%\PinyonShift\source\*\.local\preview\user\**\ForzaProfile\ForzaProfile`
and pass its enclosing `.local\preview` directory as `-StateRoot`. Never copy,
move, delete, reset, or overwrite save files merely to launch a test.
