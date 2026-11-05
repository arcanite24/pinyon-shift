"""Copy the game executables out of a disc image, checked against the supported dump.

Windows setup (tools/setup-preview.ps1) runs it so the translation can start
while extract-xiso copies the rest of the game in the background; Linux and
macOS call pinyon_setup.copy_executables directly. Reads the image only.

    python tools/copy-disc-executables.py --iso game.iso --output .local/game/base
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The pinned Windows Python is an embedded one, which does not put the
# script's folder on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_setup  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        pinyon_setup.copy_executables(args.iso, args.output)
    except pinyon_setup.SetupError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
