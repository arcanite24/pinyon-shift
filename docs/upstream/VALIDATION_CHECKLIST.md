# Normalized point-sample precision validation

Use this checklist before submitting the upstream pull request.

## Build and provenance

- [x] Apply all ReXGlue patches from the pinned base commit.
- [x] Confirm patch `0038` applies without fuzz that changes its target logic.
- [x] Build the ReXGlue code generator in Release mode.
- [x] Generate the three recompilation trees.
- [x] Build the Pinyon Shift preview in Release mode.
- [x] Confirm the build manifest reports 38 ReXGlue patches.

## Forza Horizon validation

- [x] Reach the main menu.
- [x] Load an existing save.
- [x] Enter open-world gameplay.
- [x] Confirm the under-car striped artifact is gone.
- [x] Confirm the normal vehicle shadow or ambient occlusion remains visible.
- [x] Check the HUD and minimap.
- [x] Check transparent and alpha-tested geometry.
- [x] Check lighting during movement and camera changes.
- [x] Check vehicle motion blur.
- [x] Complete normal driving without a new crash or hang.

## Evidence still needed for the public PR

- [ ] Capture a before screenshot.
- [ ] Capture a matching after screenshot.
- [ ] Add image links to the PR body.
- [ ] Confirm whether the maintainer prefers the current ReXGlue 0.10
  adaptation or a larger depth-resolve provenance port.

## Regression note

The tested implementation is broader than Xenia Canary PR #1158 because it
does not track depth-resolve provenance. It affects normalized fixed-point
samples only when point filtering is explicitly encoded in the fetch
instruction. No visible regression was observed during the reported Forza
Horizon test, but broader title coverage should be considered before merging
this behavior into a general-purpose ReXGlue release.
