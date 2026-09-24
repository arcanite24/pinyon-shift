"""Check exact-output scene probes, including a bounded continuous run."""

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
    triangle = "--triangle" in sys.argv[2:]
    continuous = "--continuous" in sys.argv[2:]
    assert not continuous or triangle, "continuous capture requires --triangle"
    images = [pixels(output / f"track-source-{frame}.ppm")
              for frame in (range(5000, 5012) if continuous else (5000, 5001, 5002))]
    assert images[0] != images[0][:3] * (1280 * 720), "missing compatibility frame"
    if continuous:
        assert images[-1] != images[-1][:3] * (1280 * 720), "missing whole-frame fallback"
    for frame, image in enumerate(images[1:-1] if continuous else images[1:], 5001):
        blue = 64 if frame % 2 else 191
        if triangle:
            sky = bytes((28, 56, 110))
            triangle_color = image[(360 * 1280 + 640) * 3:(360 * 1280 + 641) * 3]
            assert triangle_color[1:] == bytes((204, 51 if blue == 64 else 204)), frame
            assert 0 < triangle_color[0] < 255, frame
            assert image.count(sky) == 699494 and image.count(triangle_color) == 222106, frame
        else:
            color = image[:3]
            assert 0 < color[0] < 255 and color[1:] == bytes((96, blue)), color
            assert image == color * (1280 * 720), "scene output was not claimed"
    print(f"native scene handoff: fallback and {len(images) - (2 if continuous else 1)} claimed frames passed")
