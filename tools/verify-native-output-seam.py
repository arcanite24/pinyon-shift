"""Check the opt-in D3D12 output-selection probe against compatibility."""

import sys
from pathlib import Path


def pixels(path: Path) -> bytes:
    data = path.read_bytes()
    header = b"P6\n1280 720\n255\n"
    assert data.startswith(header), f"unexpected PPM header: {path}"
    image = data[len(header) :]
    assert len(image) == 1280 * 720 * 3, f"unexpected image size: {path}"
    return image


if __name__ == "__main__":
    control, probe = map(Path, sys.argv[1:3])
    first = pixels(probe / "first.ppm")
    second = pixels(probe / "second.ppm")
    colors = [first[:3], second[:3]]
    assert set(colors) == {bytes((32, 96, 64)), bytes((32, 96, 191))}, colors
    assert all(frame == color * (1280 * 720)
               for frame, color in zip((first, second), colors)), "probe was not uniform"
    assert pixels(control / "first.ppm") != first, "compatibility image was replaced"
    print("native output seam: compatibility fallback and adjacent claimed frames passed")
