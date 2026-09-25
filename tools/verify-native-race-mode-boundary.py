"""Check that live native output stays confined to active race gameplay."""

import sys
from pathlib import Path


HEADER = b"P6\n1280 720\n255\n"
NATIVE_SKY = bytes((28, 56, 110))


def capture_stats(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(HEADER), f"unexpected capture format: {path}"
    assert len(data) == len(HEADER) + 1280 * 720 * 3, f"wrong capture size: {path}"
    pixels = data[len(HEADER) :]
    return pixels.count(NATIVE_SKY), sum(pixels) // len(pixels)


if __name__ == "__main__":
    captures = Path(sys.argv[1])
    for name in ("race-sustained", "race-sustained-again"):
        path = captures / f"{name}.ppm"
        if name == "race-sustained" or path.exists():
            count, _ = capture_stats(path)
            assert count > 1000, f"native race output missing: {name} ({count} pixels)"
    for name in ("race-paused", "free-roam-after-retire", "title-settled"):
        count, mean = capture_stats(captures / f"{name}.ppm")
        assert count < 1000, f"native output leaked into {name} ({count} pixels)"
        if name != "race-paused":
            assert mean > 20, f"{name} is still a loading/blank frame (mean {mean})"
    print("native race mode boundary: race active; pause, free roam, and title compatible")
