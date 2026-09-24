"""Check that live native output stays confined to active race gameplay."""

import sys
from pathlib import Path


HEADER = b"P6\n1280 720\n255\n"
NATIVE_SKY = bytes((28, 56, 110))


def native_sky_pixels(path: Path) -> int:
    data = path.read_bytes()
    assert data.startswith(HEADER), f"unexpected capture format: {path}"
    assert len(data) == len(HEADER) + 1280 * 720 * 3, f"wrong capture size: {path}"
    return data[len(HEADER) :].count(NATIVE_SKY)


if __name__ == "__main__":
    captures = Path(sys.argv[1])
    for name in ("race-sustained", "race-sustained-again"):
        path = captures / f"{name}.ppm"
        if name == "race-sustained" or path.exists():
            count = native_sky_pixels(path)
            assert count > 1000, f"native race output missing: {name} ({count} pixels)"
    for name in ("race-paused", "free-roam-after-retire", "title-settled"):
        count = native_sky_pixels(captures / f"{name}.ppm")
        assert count < 1000, f"native output leaked into {name} ({count} pixels)"
    print("native race mode boundary: race active; pause, free roam, and title compatible")
