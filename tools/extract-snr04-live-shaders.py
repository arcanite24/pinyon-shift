"""Extract a verified 1x1 vertex corpus for live SNR-04 diagnostics."""

import argparse
import importlib.util
from pathlib import Path
import sys


spec = importlib.util.spec_from_file_location(
    "native_shader_pack", Path(__file__).with_name("native-shader-pack.py"))
pack_format = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pack_format
spec.loader.exec_module(pack_format)


def extract(pack: Path, output: Path) -> int:
    data = pack.read_bytes()
    metadata = pack_format.verify_pack(data)
    assert metadata["draw_resolution_scale_x"] == 1
    assert metadata["draw_resolution_scale_y"] == 1
    output = output.resolve()
    assert ".local" in output.parts, "diagnostic shaders must stay under .local"
    output.mkdir(parents=True, exist_ok=True)
    header = pack_format.HEADER.unpack_from(data)
    lines = ["fixture 0\n"]  # Live frames verify each used shader, not a fixture digest.
    for index in range(header[4]):
        entry = pack_format.ENTRY.unpack_from(
            data, header[5] + index * pack_format.ENTRY.size)
        stage, _, guest_hash, specialization, offset, length = entry[:6]
        if stage != pack_format.STAGES["vertex"]:
            continue
        name = f"vertex_{guest_hash:016X}_{specialization:016X}.dxil"
        bytecode = data[header[6] + offset:header[6] + offset + length]
        path = output / name
        if path.exists():
            assert path.read_bytes() == bytecode, f"existing shader differs: {name}"
        else:
            path.write_bytes(bytecode)
        lines.append(f"{entry[10].hex()} {name}\n")
    (output / "manifest.sha256").write_text("".join(lines), encoding="ascii")
    return len(lines) - 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"verified vertex shaders: {extract(args.pack, args.output)}")
