"""Check exact-output fallback and two adjacent scene-gated probe frames."""

import sys
from collections import Counter
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
    triangle = len(sys.argv) > 2 and sys.argv[2] == "--triangle"
    images = [pixels(output / f"track-source-{frame}.ppm")
              for frame in (5000, 5001, 5002)]
    assert images[0] != images[0][:3] * (1280 * 720), "missing compatibility frame"
    for image, blue in zip(images[1:], (64, 191)):
        if triangle:
            colors = Counter(image[i:i + 3] for i in range(0, len(image), 3))
            assert len(colors) == 2 and bytes((28, 56, 110)) in colors, colors
            triangle_color = next(color for color in colors if color != bytes((28, 56, 110)))
            assert triangle_color[1:] == bytes((204, 51 if blue == 64 else 204)), colors
            assert 0 < triangle_color[0] < 255, colors
        else:
            color = image[:3]
            assert 0 < color[0] < 255 and color[1:] == bytes((96, blue)), color
            assert image == color * (1280 * 720), "scene output was not claimed"
    print("native scene handoff: fallback and two adjacent source frames passed")
