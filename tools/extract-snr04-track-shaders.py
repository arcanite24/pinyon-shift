"""Extract the exact track vertex translations used by an owned T2 scene."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys


TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "native_shader_pack", TOOLS / "native-shader-pack.py")
pack_format = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pack_format
spec.loader.exec_module(pack_format)
read_fixture = runpy.run_path(str(TOOLS / "verify-snr02-track-geometry.py"))["read_fixture"]


def extract(fixture: Path, pack: Path, output: Path) -> dict:
    fixture_bytes = fixture.read_bytes()
    source, _, _, _, draws, magic = read_fixture(fixture)
    assert magic == b"SNR02T2\0" and draws
    needed = {(record[0][1], record[1][0]) for record in draws.values()}
    data = pack.read_bytes()
    metadata = pack_format.verify_pack(data)
    assert metadata["draw_resolution_scale_x"] == 1
    assert metadata["draw_resolution_scale_y"] == 1
    header = pack_format.HEADER.unpack_from(data)
    found = {}
    for index in range(header[4]):
        entry = pack_format.ENTRY.unpack_from(
            data, header[5] + index * pack_format.ENTRY.size)
        stage, _, guest_hash, specialization, offset, length = entry[:6]
        identity = (guest_hash, specialization)
        if stage != pack_format.STAGES["vertex"] or identity not in needed:
            continue
        assert identity not in found
        bytecode = data[header[6] + offset:header[6] + offset + length]
        digest = hashlib.sha256(bytecode).digest()
        assert digest == entry[10] and bytecode.startswith(b"DXBC")
        found[identity] = (bytecode, digest.hex().upper())
    assert set(found) == needed, f"missing {len(needed - found.keys())} track shaders"
    output = output.resolve()
    assert ".local" in output.parts, "diagnostic shaders must stay under .local"
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for (guest_hash, specialization), (bytecode, digest) in sorted(found.items()):
        name = f"vertex_{guest_hash:016X}_{specialization:016X}.dxil"
        path = output / name
        if path.exists():
            assert path.read_bytes() == bytecode, f"existing shader differs: {name}"
        else:
            path.write_bytes(bytecode)
        entries.append({"guest_hash": f"{guest_hash:016X}",
                        "specialization": f"{specialization:016X}",
                        "file": name, "sha256": digest,
                        "bytes": len(bytecode)})
    result = {"schema": "pinyon-shift.snr04-track-shaders.v1",
              "source_frame": source,
              "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest().upper(),
              "pack_sha256": metadata["pack_sha256"],
              "entries": entries}
    (output / "manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {"source_frame": source, "shaders": len(entries),
            "bytecode_bytes": sum(entry["bytes"] for entry in entries),
            "pack_sha256": metadata["pack_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("pack", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(extract(args.fixture, args.pack, args.output), sort_keys=True))
