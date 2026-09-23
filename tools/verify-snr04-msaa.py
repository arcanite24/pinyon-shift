"""Check four-sample private diagnostic files agree with their summary."""

from array import array
import json
from pathlib import Path
import struct
import sys


def verify(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text())
    segment = summary["schema"] == "pinyon-shift.snr04-segment.v1"
    assert segment or (summary["samples"] == 4 and summary["items"] > 0)
    pixels = 1280 * 720 if segment else summary["width"] * summary["height"]
    max_id = summary["first_id"] + summary["draws"] - 1 if segment else summary["items"]
    masks = (directory / "coverage.u8").read_bytes()
    identities = array("H")
    identities.frombytes((directory / "identity.u16x4").read_bytes())
    depths = array("f")
    depths.frombytes((directory / "depth.f32x4").read_bytes())
    sample_zero_depths = (directory / "depth.f32").read_bytes()
    ppm = (directory / "identity.ppm").read_bytes().split(b"\n", 3)
    assert ppm[:3] == [b"P6", b"1280 720" if segment else
                        f'{summary["width"]} {summary["height"]}'.encode(), b"255"]
    colors = ppm[3]
    assert len(masks) == pixels and len(identities) == len(depths) == pixels * 4
    assert len(colors) == pixels * 3 and len(sample_zero_depths) == pixels * 4
    covered = covered_any = covered_samples = 0
    for pixel in range(pixels):
        ids = identities[pixel * 4:pixel * 4 + 4]
        mask = sum((id != 0) << sample for sample, id in enumerate(ids))
        assert mask == masks[pixel] and all(id <= max_id for id in ids)
        assert all(0 <= depth <= 1 for depth in depths[pixel * 4:pixel * 4 + 4])
        covered += ids[0] != 0
        covered_any += mask != 0
        covered_samples += sum(id != 0 for id in ids)
        assert colors[pixel * 3:pixel * 3 + 3] == bytes((ids[0] & 255, ids[0] >> 8, 0))
        assert sample_zero_depths[pixel * 4:pixel * 4 + 4] == struct.pack(
            "<f", depths[pixel * 4])
    assert covered == summary["covered_pixels"]
    if not segment:
        assert (covered_any, covered_samples) == (
            summary["covered_any_pixels"], summary["covered_samples"])
    return {"fixture_sha256": summary["fixture_sha256"], "raster_draws":
            summary["draws"] if segment else summary["raster_draws"],
            "covered_pixels": covered,
            "covered_any_pixels": covered_any, "covered_samples": covered_samples}


if __name__ == "__main__":
    assert len(sys.argv) == 2, "usage: verify-snr04-msaa.py OUTPUT_DIR"
    print(json.dumps(verify(Path(sys.argv[1])), sort_keys=True))
