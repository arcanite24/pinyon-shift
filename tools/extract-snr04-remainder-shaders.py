"""Extract exact vertex translations for a verified remainder fixture."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy


TOOLS = Path(__file__).resolve().parent
verify = runpy.run_path(str(TOOLS / "verify-snr03-remainder-fixture.py"))["verify"]
pack = runpy.run_path(str(TOOLS / "extract-snr04-track-shaders.py"))["pack_format"]


def extract(fixture, log, ledger, shader_pack, output):
    verified = verify(fixture, log, ledger)
    needed = {(int(shader, 16), int(mask, 16))
              for shader, mask in verified["shader_pairs"]}
    source = shader_pack.read_bytes()
    metadata = pack.verify_pack(source)
    assert metadata["draw_resolution_scale_x"] == 1
    assert metadata["draw_resolution_scale_y"] == 1
    header = pack.HEADER.unpack_from(source)
    found = {}
    for i in range(header[4]):
        entry = pack.ENTRY.unpack_from(source, header[5] + i * pack.ENTRY.size)
        stage, _, shader, mask, offset, length = entry[:6]
        key = (shader, mask)
        if stage != pack.STAGES["vertex"] or key not in needed:
            continue
        assert key not in found
        bytecode = source[header[6] + offset:header[6] + offset + length]
        digest = hashlib.sha256(bytecode).digest()
        assert bytecode.startswith(b"DXBC") and digest == entry[10]
        found[key] = (bytecode, digest.hex())
    assert set(found) == needed, f"missing {len(needed - found.keys())} shaders"
    output = output.resolve()
    assert ".local" in output.parts
    output.mkdir(parents=True, exist_ok=True)
    lines = [f"fixture {verified['fixture_sha256']}\n"]
    for (shader, mask), (bytecode, digest) in sorted(found.items()):
        name = f"vertex_{shader:016X}_{mask:016X}.dxil"
        path = output / name
        if path.exists():
            assert path.read_bytes() == bytecode, f"changed shader: {name}"
        else:
            path.write_bytes(bytecode)
        lines.append(f"{digest} {name}\n")
    (output / "manifest.sha256").write_text("".join(lines), encoding="ascii")
    return {"shaders": len(found), "pack_sha256": metadata["pack_sha256"],
            "fixture_sha256": verified["fixture_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fixture", "log", "ledger", "pack", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(extract(args.fixture, args.log, args.ledger,
                             args.pack, args.output), sort_keys=True))
