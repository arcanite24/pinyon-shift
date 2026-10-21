# Racing wheel support files

The racing wheel path (#337) lets a wheel base, pedals and buttons each come from
their own USB device and plays FH1's own Xbox 360 wheel force feedback. Players set
it up in the launcher's **Wheel** screen (`launcher/PinyonShift.Launcher/Wheel`):
**Wheel** on the main screen, or **Settings > Configure Wheel**. The player docs are
in [site/pages/playing.md](../../site/pages/playing.md#racing-wheels), and how the
game drives a force feedback wheel is in `site/findings/systems.toml`, group *Wheel
force feedback*.

This folder holds what builds and supports that screen.

| Path | What it is |
| --- | --- |
| `build-sdl.ps1` | Builds `SDL3.dll` for the Wheel screen from the SDK's own SDL3 source, so joystick names, paths and numbering match the game's. `tools/package-launcher.ps1` runs it when `launcher/PinyonShift.Launcher/Wheel/Native/SDL3.dll` is missing. It fetches the SDK's `thirdparty/sdl3` submodule if a checkout lacks it, and uses Visual Studio's CMake generator when Ninja is not on `PATH`. Needs the VS 2022 C++ build tools and CMake. |
| `native/CMakeLists.txt` | The SDL3 build: the SDK's subsystem options with only input and haptics on. |
| `scripts/collect-wheel-logs.ps1` | Zips the wheel lines of the runtime log, the newest force feedback trace and the `wheel_*` config lines onto the Desktop, for bug reports. No game files or saves. |
| `scripts/analyze_ffb_trace.py` | Summarises a force feedback trace (`wheel_ffb_trace`): the effects the game downloaded and how the forces moved. |
| `scripts/ffb-tune.ps1` | Shows or changes the force feedback settings in the config (strength, direction, rumble, scale, trace). |
| `scripts/set-ffb-scale.ps1` | Sets `wheel_ffb_magnitude_max`, the scale of the game's effect values. |

The scripts find the launcher's install folder on their own (`install-root.txt`, else
`%LOCALAPPDATA%\PinyonShift`); `-Install <folder>` overrides it.

## Testing the Wheel screen without a wheel

```text
PinyonShiftLauncher.exe --wheel-selftest <pinyon_shift.toml> <folder>
```

opens the Wheel screen on that config, plugs in SDL virtual devices (a wheel base, a
pedal set and a button box), drives the guided setup, single binds, a second input on
one button and the telemetry card, saves screenshots and `selftest.log` to the folder
and quits.

## Settings it writes

All in `pinyon_shift.toml`, read by shiftglue-sdk's SDL input driver:
`wheel_enabled` (the raw wheel path; off by default), `wheel_device`,
`wheel_steering_axis`, `wheel_throttle`, `wheel_brake`, `wheel_clutch`,
`wheel_buttons` (`NAME=input`, repeatable for several inputs on one button),
the per-pedal `wheel_<pedal>_deadzone_bottom` / `_top`, and the `wheel_ffb_*`
force feedback settings. shiftglue-sdk's `docs/RACING_WHEELS.md` describes each one,
with its default, and how devices and inputs are named.
