"""Check exact-output fallback and two adjacent scene-gated probe frames."""

import sys
from pathlib import Path


def pixels(path: Path) -> bytes:
    data = path.read_bytes()
    header = b"P6\n1280 720\n255\n"
    assert data.startswith(header), path
    image = data[len(header) :]
    assert len(image) == 1280 * 720 * 3, path
    return image


if __name__ == "__main__":
    output = Path(sys.argv[1])
    images = [pixels(output / f"track-source-{frame}.ppm")
              for frame in (5000, 5001, 5002)]
    assert images[0] != images[0][:3] * (1280 * 720), "missing compatibility frame"
    for image, blue in zip(images[1:], (64, 191)):
        color = image[:3]
        assert 0 < color[0] < 255 and color[1:] == bytes((96, blue)), color
        assert image == color * (1280 * 720), "scene output was not claimed"
    print("native scene handoff: fallback and two adjacent source frames passed")
