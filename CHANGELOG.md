# Changelog

## 0.1.0 - Unreleased

- First Windows public playable preview.
- Updated the pinned ReXGlue SDK from 0.9.0 to 0.10.0, including its threading,
  audio, input, GPU, diagnostics, and incremental-codegen improvements, while
  preserving the project's runtime compatibility patch set.
- Added a graphical launcher that verifies a supported disc and performs the
  complete local toolchain, extraction, generation, and build workflow.
- Added reproducible dependency pins and a public-source repository boundary.
- Added resilient ReXGlue/submodule download retries, disabled SDL's optional
  libusb probe on Windows, and made Xbox menu acceptance accessible through
  Space or left click with an in-launcher control hint.
- Restored motion blur around the player car and removed the stale gameplay
  limitation list after the latest compatibility fixes.
- Added launcher controls for validated graphics experiments, including 2x
  resolution scaling, anisotropic filtering, and post-effect selection.
