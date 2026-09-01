# Troubleshooting

## The ISO is rejected

Only the USA retail base disc listed in `config/supported-dumps.json` is
supported. A bad dump, another region, a title update, or a modified image will
not match. The launcher does not accept nearly matching images and cannot
download or repair one.

## Setup asks for administrator permission

Elevation is needed only when the Microsoft C++ Build Tools are absent. The
launcher itself, downloads, disc extraction, generation, build, saves, and logs
remain in user-writable folders.

## Windows warns about an unrecognized app

Preview launchers are not code-signed yet, so Microsoft Defender SmartScreen may
show an unrecognized-app warning. Download only from this repository's Releases
page and compare the ZIP's SHA-256 with the value published in the release notes
before deciding whether to run it.

## A download fails

Check the internet connection and run the launcher again. ReXGlue and its
submodules are retried automatically after transient GitHub/network failures.
Partially downloaded files are not trusted; every pinned archive is SHA-256
verified before use.

## The build fails

Restart Windows after a Build Tools installation, make at least 25 GB free, and
close every running Pinyon Shift preview before trying again. If it still
fails, choose **Open logs** in the launcher and attach `launcher.log` to the bug
report. This log contains build output and local paths, but no game data or
generated source. Never attach game files or generated source.

## Gameplay stutters

Some one-time stutter while the preview encounters new effects is expected in
this early release. If severe stutter continues after revisiting the same route,
report whether it happens only on the first pass or every pass and include the
latest performance CSV and runtime log from `.local/preview/logs`. Those two
cases have different causes, and the measurements are needed for a targeted
fix.

## The game does not start

Update the GPU driver and confirm that the GPU supports DirectX 12. Remove
`.local/preview/config/pinyon_shift.toml` to reset runtime settings. Security
software may also quarantine a newly compiled unsigned executable; restore it
only after confirming it was produced by your local checkout.

## A controller is not recognized

Connect the controller before starting the game. Pinyon Shift uses SDL mappings
for DirectInput devices and includes an explicit mapping for the 8BitDo Ultimate
2C Wired Controller (`2dc8:301d`). If that model still does not respond, confirm
that `gamecontrollerdb.txt` is beside `pinyon_shift.exe`, close Steam or other
controller-remapping software temporarily, reconnect the controller, and relaunch.

When reporting another unsupported controller, include its exact name, USB
vendor/product IDs, button count, axis count, and a screenshot from a gamepad
tester. Do not attach input recordings.

## A selected Xbox menu item does not respond

Xbox menus do not use Windows pointer targeting. Use controller A or Space to
activate the selected item. Pinyon Shift also maps a left click to controller A,
so clicking while `SIGN IN` or another row is selected activates that row.
Press Enter for the Xbox Start button.

## The game crashes

Leave the launcher open while playing. It will prepare a sanitized ZIP under
`.local/preview/reports`, select that file in Explorer, and open a prefilled
GitHub issue. Attach the ZIP and describe the last actions before the crash.

Memory dumps under `.local/preview/crashes` may contain process-memory fragments
and are never placed in the public report. Keep them local unless a maintainer
arranges a private transfer for a specific investigation.

## Start over

Close the launcher and delete `.local` and `out` from the repository or the
launcher source folder under `%LOCALAPPDATA%\PinyonShift`. Your original ISO is
outside those folders and is never deleted by project scripts.

## Uninstall completely

Close the launcher and preview, then delete the extracted launcher folder and
`%LOCALAPPDATA%\PinyonShift`. The preview does not install a Windows service or
registry startup entry. Microsoft Visual Studio Build Tools are shared system
tools and should be removed separately from **Installed apps** only if no other
development work uses them. The original ISO remains wherever you stored it.
