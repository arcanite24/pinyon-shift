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

Check the internet connection and run the launcher again. Partially downloaded
files are not trusted; every pinned archive is SHA-256 verified before use.

## The build fails

Restart Windows after a Build Tools installation, make at least 25 GB free, and
try again. If it still fails, open the build log from the launcher and include
the last relevant lines in a bug report. Never attach game files or generated
source.

## The game does not start

Update the GPU driver and confirm that the GPU supports DirectX 12. Remove
`.local/preview/config/pinyon_shift.toml` to reset runtime settings. Security
software may also quarantine a newly compiled unsigned executable; restore it
only after confirming it was produced by your local checkout.

## Start over

Close the launcher and delete `.local` and `out` from the repository or the
launcher source folder under `%LOCALAPPDATA%\PinyonShift`. Your original ISO is
outside those folders and is never deleted by project scripts.
