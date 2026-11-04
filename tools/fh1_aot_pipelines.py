#!/usr/bin/env python3
"""Ahead-of-time Vulkan pipelines for FH1 (docs/AOT_PIPELINE_BACKLOG.md).

The pipelines a drive needs are known from earlier play, but building them
needs the guest shaders, which are game data. So the repository keeps only a
catalog (config/fh1-aot-pipelines.json): the pipeline descriptions, by shader
hash, and for each shader the disc program it comes from, by SHA-256, with
the structural edits that turn it into the shader the title draws with
(exports disabled, retargeted or a fetch reformatted). At setup `generate`
rebuilds the shaders from the player's own disc corpus and writes
<title>.fbo.aot.xpso, which ShiftGlue builds behind the title.

  fh1_aot_pipelines.py catalog --corpus DIR --storage DIR [--storage DIR...]
                               --output FILE
  fh1_aot_pipelines.py generate --corpus DIR --catalog FILE --output FILE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = "pinyon-shift.fh1-aot-pipelines.v1"
# PipelineDescription::kVersion in ShiftGlue's Vulkan pipeline cache.
DESCRIPTION_VERSION = 0x20261018
PORTABLE = 58
# An instruction the title's linking turns off: an export to nowhere.
NOP = bytes.fromhex("c80000000000000002000000")
STAGES = {"vertex": 0, "pixel": 1}


def read_corpus(directory: Path) -> dict[tuple[int, str], bytes]:
    """{(stage, SHA-256): program} from extract-fh1-shader-corpus.py output."""
    blob = (directory / "corpus.blob").read_bytes()
    magic, _, count = struct.unpack_from("<4sII", blob, 0)
    if magic != b"FH1C":
        raise ValueError(f"not a shader corpus: {directory}")
    programs, offset = {}, 12
    for _ in range(count):
        stage, _, _, size = struct.unpack_from("<BBHI", blob, offset)
        offset += 8
        code = blob[offset : offset + size]
        offset += size
        programs[1 if stage == 1 else 0, hashlib.sha256(code).hexdigest().upper()] = code
    return programs


def read_shaders(path: Path) -> dict[int, tuple[int, bytes]]:
    """{XXH3: (stage, microcode)} from a .xsh shader storage file."""
    data, shaders, offset = path.read_bytes(), {}, 8
    while offset + 12 <= len(data):
        ucode_hash, packed = struct.unpack_from("<QI", data, offset)
        size = (packed & 0x7FFFFFFF) * 4
        shaders[ucode_hash] = (packed >> 31, data[offset + 12 : offset + 12 + size])
        offset += 12 + size
    return shaders


def read_descriptions(directory: Path) -> set[bytes]:
    """Stored descriptions in the portable layout, texture signs dropped."""
    found = set()
    for path in directory.glob("*.fbo.vk.xpso"):
        data = path.read_bytes()
        if data[:4] != b"XEPS" or (len(data) - 12) % 68:
            continue
        # MSVC's 60 bytes: the last 15 bits of the bitfields in a unit of their own.
        found |= {data[o + 8 : o + 50] + data[o + 52 : o + 68] for o in range(12, len(data), 68)}
    for path in directory.glob("*.fbo.vk.signs.xpso"):
        data = path.read_bytes()
        for record in (98, 100):  # clang, MSVC
            if data[:4] == b"XEPT" and (len(data) - 8) % record == 0:
                for o in range(8, len(data), record):
                    d = data[o + 8 : o + record - 32]
                    found.add(d if len(d) == PORTABLE else d[:42] + d[44:])
                break
    return found


def recipe(code: bytes, base: bytes) -> list:
    """Edits from base to code: [instruction] disables it, [dword, xor] flips bits."""
    edits = []
    for instruction in range(0, len(code), 12):
        new, old = code[instruction : instruction + 12], base[instruction : instruction + 12]
        if new == old:
            continue
        if new == NOP:
            edits.append([instruction // 12])
            continue
        for word in range(instruction, min(instruction + 12, len(code)), 4):
            a, b = struct.unpack_from(">I", base, word)[0], struct.unpack_from(">I", code, word)[0]
            if a != b:
                edits.append([word // 4, a ^ b])
    return edits


def apply(base: bytes, edits: list) -> bytes:
    code = bytearray(base)
    for edit in edits:
        if len(edit) == 1:
            code[edit[0] * 12 : edit[0] * 12 + 12] = NOP
        else:
            word = struct.unpack_from(">I", code, edit[0] * 4)[0] ^ edit[1]
            struct.pack_into(">I", code, edit[0] * 4, word)
    return bytes(code)


def catalog(corpus: Path, storages: list[Path], output: Path) -> dict:
    programs = read_corpus(corpus)
    by_size = defaultdict(list)
    for (stage, digest), code in programs.items():
        by_size[stage, len(code)].append((digest, code))
    shaders, descriptions = {}, set()
    for storage in storages:
        for path in storage.glob("*.xsh"):
            shaders.update(read_shaders(path))
        descriptions |= read_descriptions(storage)

    sources, unresolved = {}, 0
    for ucode_hash, (stage, code) in shaders.items():
        digest = hashlib.sha256(code).hexdigest().upper()
        if (stage, digest) in programs:
            sources[ucode_hash] = [stage, digest, []]
            continue
        best = None
        for base_digest, base in by_size.get((stage, len(code)), ()):
            edits = recipe(code, base)
            if best is None or len(edits) < len(best[1]):
                best = base_digest, edits
        # A quarter of the words at most: beyond that it is another program.
        if best and len(best[1]) <= max(4, len(code) // 16):
            assert apply(programs[stage, best[0]], best[1]) == code
            sources[ucode_hash] = [stage, best[0], best[1]]
        else:
            unresolved += 1

    kept = sorted(d for d in descriptions
                  if struct.unpack_from("<Q", d, 0)[0] in sources and
                  (not struct.unpack_from("<Q", d, 16)[0] or
                   struct.unpack_from("<Q", d, 16)[0] in sources))
    used = {struct.unpack_from("<Q", d, o)[0] for d in kept for o in (0, 16)} - {0}
    result = {
        "schema": SCHEMA,
        "description_version": f"{DESCRIPTION_VERSION:08X}",
        "shaders": {f"{h:016X}": [("vertex", "pixel")[s[0]], s[1], s[2]]
                    for h, s in sorted(sources.items()) if h in used},
        "pipelines": [d.hex().upper() for d in kept],
    }
    output.write_text(json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"shaders": len(result["shaders"]), "unresolved_shaders": unresolved,
            "pipelines": len(kept), "dropped_pipelines": len(descriptions) - len(kept)}


def expand(pipelines: list[bytes]) -> list[bytes]:
    """Each shader pair in every state block seen with its vertex or pixel shader."""
    pairs, by_vertex, by_pixel = set(), defaultdict(set), defaultdict(set)
    for d in pipelines:
        pairs.add(d[:32])
        by_vertex[d[0:16]].add(d[32:])
        by_pixel[d[16:32]].add(d[32:])
    return sorted({pair + state for pair in pairs
                   for state in by_vertex[pair[0:16]] | by_pixel[pair[16:32]]})


def generate(corpus: Path, catalog_path: Path, output: Path, expand_states: bool = True) -> dict:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or int(data["description_version"], 16) != DESCRIPTION_VERSION:
        raise ValueError(f"unsupported AOT pipeline catalog: {catalog_path}")
    programs = read_corpus(corpus)
    shaders = {}
    for name, (stage, digest, edits) in data["shaders"].items():
        base = programs.get((STAGES[stage], digest))
        if base is not None:
            shaders[int(name, 16)] = (STAGES[stage], apply(base, edits))
    pipelines = [bytes.fromhex(d) for d in data["pipelines"]]
    pipelines = [d for d in pipelines
                 if struct.unpack_from("<Q", d, 0)[0] in shaders and
                 (not struct.unpack_from("<Q", d, 16)[0] or
                  struct.unpack_from("<Q", d, 16)[0] in shaders)]
    if expand_states:
        pipelines = expand(pipelines)
    body = bytearray(struct.pack("<4sIII", b"XEAO", DESCRIPTION_VERSION, len(shaders),
                                 len(pipelines)))
    for ucode_hash, (stage, code) in sorted(shaders.items()):
        body += struct.pack("<QI", ucode_hash, len(code) // 4 | stage << 31) + code
    for d in pipelines:
        body += d
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(bytes(body))
    temporary.replace(output)
    return {"shaders": len(shaders), "catalog_shaders": len(data["shaders"]),
            "pipelines": len(pipelines)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("catalog", help="build the catalog from stored pipelines")
    build.add_argument("--corpus", type=Path, required=True)
    build.add_argument("--storage", type=Path, action="append", required=True,
                       help="a shareable shader storage folder (.xsh, .vk.xpso)")
    build.add_argument("--output", type=Path, required=True)
    write = commands.add_parser("generate", help="write the pipelines from the player's disc")
    write.add_argument("--corpus", type=Path, required=True)
    write.add_argument("--catalog", type=Path, required=True)
    write.add_argument("--output", type=Path, required=True)
    write.add_argument("--no-expand", action="store_true",
                       help="only the pipelines seen, not their shaders in each other's states")
    args = parser.parse_args()
    if args.command == "catalog":
        result = catalog(args.corpus, args.storage, args.output)
    else:
        result = generate(args.corpus, args.catalog, args.output, not args.no_expand)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
