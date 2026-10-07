#!/usr/bin/env python3
"""List code addresses built as function pointers that ReXGlue did not emit.

A lis/addi pair in .pdata code, or a data word such as a vtable slot, can hold
the address of a short thunk outside any .pdata function (argument swaps,
this-adjustments, virtual-call stubs).
If the analysis misses one, an indirect call reaches an unregistered target at
runtime (M3_TRACE indirect.unregistered). This scans executable sections for
such referenced code, follows its reachable paths to find its extent, and
reports addresses the generated init table does not register, with their
sizes, as TOML ready for review.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V4MAP = load("v4map", "tools/map-fh1-v4-addresses.py")
ADDRESSES = load("v4addresses", "tools/generate-fh1-v4-addresses.py")


def extent(image, start: int, limit: int = 0x800) -> int | None:
    """Bytes reachable from `start` before every path returns or tail-branches.

    Follows conditional branches inside [start, start + limit); calls fall
    through. Fails (None) on a zero word, on entering a .pdata function, or on
    a path that leaves the bound other than by a tail branch."""
    visited, stack, last = set(), [start], start
    while stack:
        pc = stack.pop()
        while True:
            if pc in visited:
                break
            if not start <= pc < start + limit or (pc != start and (pc in image.functions or image.containing(pc))):
                return None
            word = image.words[image.index(pc)]
            if word == 0:
                return None
            visited.add(pc)
            last = max(last, pc)
            op, link = word >> 26, word & 1
            if op == 16:
                displacement = word & 0xFFFC
                displacement -= 0x10000 if displacement & 0x8000 else 0
                if not link and not word & 2:
                    stack.append((pc + displacement) & 0xFFFFFFFF)
                if not link and (word >> 21) & 0x14 == 0x14:  # branch always
                    break
            elif op == 18 and not link:
                target = V4MAP.branch_target(word, pc)
                if target is not None and start <= target < start + limit:
                    stack.append(target)
                break  # tail branch or in-function jump
            elif op == 19 and (word >> 1) & 0x3FF in (16, 528) and not link and (word >> 21) & 0x14 == 0x14:
                break  # unconditional blr/bctr
            pc += 4
    return last + 4 - start


def referenced_thunks(image, ranges) -> dict[int, int]:
    refs = set()
    for start in image.starts:
        refs.update(V4MAP.absolute_refs(image, start, image.functions[start]).values())
    # Vtable slots and other data words outside executable sections.
    for index, word in enumerate(image.words):
        address = image.load + index * 4
        if not any(lo <= address < hi for lo, hi in ranges) and any(lo <= word < hi for lo, hi in ranges):
            refs.add(word)
    found = {}
    for address in refs:
        if address % 4 or address in image.functions or image.containing(address) or                 not any(lo <= address < hi for lo, hi in ranges):
            continue
        size = extent(image, address)
        if size:
            found[address] = size
    return found


def registered(generated: Path) -> set[int]:
    """Addresses the generated init table registers (including extra entries)."""
    text = (generated / "pinyon_shift_init.cpp").read_text(encoding="utf-8", errors="ignore")
    return {int(x, 16) for x in re.findall(r"\{ 0x([0-9A-F]{8}), sub_", text)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path, help="loaded image (for example .local/game/v4-images/default.v4.bin)")
    parser.add_argument("generated", type=Path, help="generated tree (for example .local/generated-v4/default)")
    parser.add_argument("--load", type=lambda v: int(v, 0), default=0x82000000)
    args = parser.parse_args()
    data = args.image.read_bytes()
    image = V4MAP.Image(data, args.load)
    emitted = registered(args.generated)
    thunks = referenced_thunks(image, ADDRESSES.executable_ranges(data, args.load))
    missing = sorted(a for a in thunks if a not in emitted)
    for address in missing:
        print(f'[functions."{address:08X}"]\nsize = 0x{thunks[address]:02X}\n')
    print(f"# {len(missing)} of {len(thunks)} referenced thunks are not emitted", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
