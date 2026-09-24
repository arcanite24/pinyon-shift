"""Check moving, upright owned race geometry in exact-output captures."""

import sys
from pathlib import Path


def pixels(path: Path) -> bytes:
    data = path.read_bytes()
    header = b"P6\n1280 720\n255\n"
    assert data.startswith(header), f"unexpected PPM header: {path}"
    image = data[len(header):]
    assert len(image) == 1280 * 720 * 3, f"wrong image size: {path}"
    return image


if __name__ == "__main__":
    output = Path(sys.argv[1])
    sky = bytes((28, 56, 110))
    car = bytes((166, 41, 31))
    half = 1280 * 360 * 3
    previous = pixels(output / "track-source-5000.ppm")
    assert previous.count(sky) < 1000, "missing compatibility control"
    for frame in range(5001, 5021):
        image = pixels(output / f"track-source-{frame}.ppm")
        sky_pixels = image.count(sky)
        assert 1000 < sky_pixels < 900000, f"missing native track geometry: {frame}"
        assert image[:half].count(sky) == sky_pixels, f"inverted scene: {frame}"
        assert image[half:].count(car) > 10000, f"missing native car: {frame}"
        assert image != previous, f"stale output frame: {frame}"
        previous = image
    if len(sys.argv) > 2:
        fallback = Path(sys.argv[2])
        for name in ("first", "second"):
            image = pixels(fallback / f"{name}.ppm")
            assert image != image[:3] * (1280 * 720), f"missing fallback: {name}"
            assert image.count(sky) < 1000, f"native output claimed without scene: {name}"
    print("native race output: 20 moving upright scene and car frames passed")
