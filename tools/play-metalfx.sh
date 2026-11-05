#!/bin/sh
# Launch the locally built game interactively on macOS with MetalFX frame
# generation and the Metal performance HUD on. No render-test script, so no
# telemetry and no perf CSV.
#
# Usage:
#   tools/play-metalfx.sh [extra game arguments...]
#
# Frame generation is off by default in the build; this turns it on. Open
# F6 > DISPLAY > FRAME GENERATION in game to toggle it live. It only runs
# while twice the game's rate fits the panel, so on a 60 Hz panel the render
# rate is capped at 30 fps here (the M1 drives at about 21 ms a frame since
# 2026-10-17). Pass --pinyon_shift_fh1_render_fps_limit=0 to run uncapped
# without generation, or --pinyon_shift_metal_hud=false to hide the HUD;
# a later argument wins.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
build="$here/out/build/macos-arm64-release"

if [ ! -x "$build/pinyon_shift" ]; then
  echo "the game is not built at $build" >&2
  echo "build it with: cmake --build out/build/macos-arm64-release" >&2
  exit 1
fi

exec python3 "$here/tools/pinyon.py" launch \
  --build-directory "$build" \
  -- \
  --present_frame_generation=metalfx \
  --pinyon_shift_fh1_render_fps_limit=30 \
  --pinyon_shift_metal_hud=true \
  "$@"
