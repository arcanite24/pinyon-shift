"""Check in-race native/compatibility switching on captured guest output."""

import sys
from pathlib import Path


output = Path(sys.argv[1])
header = b"P6\n1280 720\n255\n"
sky = bytes((28, 56, 110))
expected = {
    "before-on": False,
    "native-on": True,
    "before-off": True,
    "compatibility-off": False,
    "before-on-again": False,
    "native-on-again": True,
}
for name, native in expected.items():
    image = (output / f"{name}.ppm").read_bytes()
    assert image.startswith(header) and len(image) == len(header) + 1280 * 720 * 3
    count = image.count(sky)
    assert (count > 1000) == native, f"wrong output mode at {name}: {count}"
print("native race output: live on/off/on switching passed")
