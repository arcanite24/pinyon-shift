# Issue-work checkpoint — 2026-10-06

This checkpoint publishes the twelve completed issue-work commits through
`16ead1a` to `dev`. It does not publish a release. The remaining Rally,
Android and renderer work is preserved separately and remains uncommitted.

## Completed reports and tracker items

| Work | Commit | GitHub status |
| --- | --- | --- |
| Safe VsDevCmd temporary paths | `37dcef2` | #365 completed |
| Selected compiler/library/SDK capability checks | `ea6ac88` | #350, #372 completed; #339 still open |
| Incomplete source installation repair | `bb6f759` | #347 completed; GH-2 checked |
| Failed-session diagnostics and selected Vulkan device | `ab872dd`, `1fa7194` | GH-7 checked |
| Missing codegen logs and Unicode paths | `bdf3da5`, `dba2c21` | GH-13 checked; #362 previously closed |
| Verified extracted game folder input | `97b7968` | #358 completed; GH-19 checked |
| Early language selection instructions | `0696578` | #360 completed; GH-20 checked |

## Partial work and unresolved reports

- `3e3c96d` fixes reproduced UTF-8 BOM configuration rejection. The original
  #345/#364 configurations are unavailable; both reports and GH-3 stay open.
- `801adc8` improves opening-route synchronization. It does not qualify the
  Viper-to-Corrado transition; #327/#343 and GH-5 stay open.
- `16ead1a` adds a default-off child-ownership trace and a qualified Gauntlet
  entry/driving control. It does not fix the reported dispatch crashes.
  GH-11/GH-12 and their crash reports stay open.
- Imported saves, AMD/Intel rendering and performance, optional DoF,
  ultrawide, wheel input and macOS still require their completion gates.
- Rally's original gameplay flow and Android graphics/performance remain
  unfinished. This checkpoint does not claim those features are complete.

The public status tracker is [#354](https://github.com/arcanite24/pinyon-shift/issues/354).
There are 25 open issues, including that tracker, at this checkpoint.

## Validation and preservation

Each published change retains its prior focused regression and private-run
qualification. Checks are repeated against an isolated archive of the committed
source and pinned SDK, rather than the unfinished worktree. The repeated nine
suites pass 81 checks; one repository-metadata check is skipped because the
archive has no `.git` directory. The isolated environment initially lacked
the toolchain and SDK source; supplying the pinned dependencies resolves those
fixture failures. Native runtime
build and gameplay qualifications are recorded in the tracker; the broader
Rally/Android worktree build is not a qualification of this committed snapshot.

A local archive preserves 137 modified/new files, binary diffs, repository
HEADs and SHA-256 manifests across the main repository, SDK and libmspack.
Archive integrity and every archived file hash were verified. It contains
unfinished source work and is not part of the push. Player saves, pinned seeds
and original game inputs are untouched.
