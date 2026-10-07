#!/usr/bin/env python3
"""Map guest addresses from the base FH1 executable to its v4 title update.

Both inputs are loaded PowerPC images (see `pinyon_shift_fh1_archive_extract
--xex-image` and `--title-update-image`). Functions come from each image's
.pdata table. An address is mapped by, in order of preference:

1. `exact`: its function's body is identical in both images after masking
   branch displacements and absolute-address immediates, and that normalized
   body is unique in each image;
2. `aligned`: its function is paired through calls from exactly matched
   functions, and the address lies in an aligned run of identical normalized
   instructions;
3. `context`: a normalized instruction window around it occurs exactly once
   in each image;
4. `data`: it is a data address formed by `lis`/`addi`-style pairs at the
   same instruction in matched code, with every pairing agreeing.

Unmapped addresses are reported, never guessed. Nothing is written beside the
inputs; output goes to --output (JSON) or stdout.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import difflib
import hashlib
import json
import struct
import sys
from pathlib import Path

LOAD = 0x82000000
# D-form instructions whose 16-bit immediate can carry the low half of an
# absolute address built by a preceding `lis` into the same register.
D_FORM = {14, 24, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47,
          48, 49, 50, 51, 52, 53, 54, 55, 58, 62}


class Image:
    def __init__(self, data: bytes, load: int):
        self.data, self.load = data, load
        self.words = struct.unpack(f">{len(data) // 4}I", data[:len(data) // 4 * 4])
        self.norm = normalize(self.words)
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        start, size = struct.unpack_from("<II", data, pe + 24 + 120)
        self.functions = {}
        for begin, info in struct.iter_unpack(">II", data[start:start + size]):
            length = ((info >> 8) & 0x3FFFFF) * 4
            if begin and length and load <= begin < load + len(data):
                self.functions[begin] = length
        self.starts = sorted(self.functions)

    def index(self, address: int) -> int:
        return (address - self.load) // 4

    def body(self, start: int) -> tuple:
        first = self.index(start)
        return self.norm[first:first + self.functions[start] // 4]

    def containing(self, address: int) -> int | None:
        i = bisect.bisect_right(self.starts, address) - 1
        if i >= 0 and self.starts[i] <= address < self.starts[i] + self.functions[self.starts[i]]:
            return self.starts[i]
        return None


def normalize(words) -> tuple:
    out = list(words)
    for j, word in enumerate(words):
        op = word >> 26
        if op == 18:  # b/bl: keep opcode and AA/LK bits.
            out[j] = word & 0xFC000003
        elif op == 15 and not word & 0x1F0000:  # lis rD, imm
            out[j] = word & 0xFFFF0000
            reg = (word >> 21) & 31
            for k in range(j + 1, min(j + 9, len(words))):
                follower = words[k]
                if follower >> 26 in D_FORM and (follower >> 16) & 31 == reg:
                    out[k] = follower & 0xFFFF0000
    return tuple(out)


def branch_target(word: int, pc: int) -> int | None:
    if word >> 26 != 18 or word & 2:
        return None
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return (pc + displacement) & 0xFFFFFFFF


def absolute_refs(image: Image, start: int, length: int) -> dict[int, int]:
    """Map instruction index (within the function) to the absolute address it forms."""
    first = image.index(start)
    words = image.words[first:first + length // 4]
    refs = {}
    for j, word in enumerate(words):
        if word >> 26 != 15 or word & 0x1F0000:
            continue
        reg, high = (word >> 21) & 31, (word & 0xFFFF) << 16
        for k in range(j + 1, min(j + 9, len(words))):
            follower = words[k]
            if follower >> 26 in D_FORM and (follower >> 16) & 31 == reg:
                low = follower & 0xFFFF
                low = low - 0x10000 if low & 0x8000 and follower >> 26 != 24 else low
                refs[k] = (high + low) & 0xFFFFFFFF
    return refs


def vcall_thunks(image: Image) -> dict[int, int]:
    """Virtual-call thunks the image builds as function pointers.

    `lwz r11, 0(r3); ...; lwz r11, slot(r11); mtctr r11; bctr` outside any
    .pdata function, referenced by a lis/addi pair. ReXGlue's analysis does
    not always find these, so they are declared as functions (start -> size)."""
    refs = set()
    for start in image.starts:
        refs.update(absolute_refs(image, start, image.functions[start]).values())
    found = {}
    for address in refs:
        if address % 4 or address in image.functions or image.containing(address) or                 not image.load <= address < image.load + len(image.data) - 32:
            continue
        words = image.words[image.index(address):image.index(address) + 8]
        if words[0] != 0x81630000:
            continue
        for k in range(1, 7):
            if words[k] == 0x7D6903A6 and words[k + 1] == 0x4E800420:
                found[address] = (k + 2) * 4
                break
    return found


def shape(words) -> tuple:
    """Words with D-form displacements masked (vtable slots, field offsets)."""
    return tuple(w & 0xFFFF0000 if w >> 26 in D_FORM else w for w in words)


def reference_at(image: Image, address: int) -> int | None:
    """Absolute address formed by the D-form instruction at `address`."""
    index = image.index(address)
    follower = image.words[index]
    if follower >> 26 not in D_FORM:
        return None
    reg = (follower >> 16) & 31
    for k in range(index - 1, max(index - 9, -1), -1):
        word = image.words[k]
        if word >> 26 == 15 and not word & 0x1F0000 and (word >> 21) & 31 == reg:
            low = follower & 0xFFFF
            low = low - 0x10000 if low & 0x8000 and follower >> 26 != 24 else low
            return (((word & 0xFFFF) << 16) + low) & 0xFFFFFFFF
    return None


class Mapper:
    def __init__(self, base: Image, target: Image):
        self.base, self.target = base, target
        self.exact = self._exact()
        self.anchored = self._anchored()
        self._alignments = {}
        self.data = self._data()

    def _exact(self) -> dict[int, int]:
        index = collections.defaultdict(list)
        for start in self.target.starts:
            index[hashlib.sha1(repr(self.target.body(start)).encode()).digest()].append(start)
        seen = collections.Counter(hashlib.sha1(repr(self.base.body(s)).encode()).digest()
                                   for s in self.base.starts)
        out = {}
        for start in self.base.starts:
            key = hashlib.sha1(repr(self.base.body(start)).encode()).digest()
            if seen[key] == 1 and len(index[key]) == 1:
                out[start] = index[key][0]
        return out

    def _anchored(self) -> dict[int, int]:
        """Pair call targets at the same position in matched functions.

        Starts from exactly matched functions, then repeats through newly
        paired functions using their aligned instruction runs, until no new
        unambiguous pair appears."""
        used = set(self.exact.values())
        anchored: dict[int, int] = {}
        frontier = [(start, target, None) for start, target in self.exact.items()]
        while frontier:
            pairs = collections.defaultdict(set)
            for start, target, alignment in frontier:
                if alignment is None:
                    offsets = ((o, o) for o in range(0, self.base.functions[start], 4))
                else:
                    offsets = ((a - start, b - target) for a, b in alignment.items())
                for a_off, b_off in offsets:
                    a_pc, b_pc = start + a_off, target + b_off
                    a = branch_target(self.base.words[self.base.index(a_pc)], a_pc)
                    b = branch_target(self.target.words[self.target.index(b_pc)], b_pc)
                    if a is not None and b is not None and a in self.base.functions and b in self.target.functions:
                        pairs[a].add(b)
            new = {a: next(iter(v)) for a, v in pairs.items()
                   if len(v) == 1 and a not in self.exact and a not in anchored}
            counts = collections.Counter(new.values())
            new = {a: b for a, b in new.items() if counts[b] == 1 and b not in used}
            anchored.update(new)
            used.update(new.values())
            self.anchored = anchored
            self._alignments = getattr(self, "_alignments", {})
            frontier = [(a, b, self._alignment(a)) for a, b in new.items()]
        return anchored

    def _data(self) -> dict[int, int]:
        pairs = collections.defaultdict(set)
        for start, target in self.exact.items():
            length = self.base.functions[start]
            a_refs = absolute_refs(self.base, start, length)
            b_refs = absolute_refs(self.target, target, length)
            for k, address in a_refs.items():
                if k in b_refs:
                    pairs[address].add(b_refs[k])
        return {a: next(iter(v)) for a, v in pairs.items() if len(v) == 1}

    def _alignment(self, start: int) -> dict[int, int]:
        if start not in self._alignments:
            target = self.anchored[start]
            a, b = self.base.body(start), self.target.body(target)
            matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
            mapping = {}
            for i, j, size in matcher.get_matching_blocks():
                if size >= 4:
                    for k in range(size):
                        mapping[start + (i + k) * 4] = target + (j + k) * 4
            self._alignments[start] = mapping
        return self._alignments[start]

    def _reliable(self, address: int) -> int | None:
        """Map through exact or aligned function pairs only (no searches)."""
        start = self.base.containing(address)
        if start in self.exact:
            return self.exact[start] + (address - start)
        if start in self.anchored:
            return self._alignment(start).get(address)
        return None

    def branches_consistent(self, address: int, mapped: int, count: int) -> bool:
        """Direct branches in the range reach the mapped counterparts of their
        base targets wherever those targets map reliably. Masked branches make
        runs of small thunks look identical, so this pins the right one."""
        a, b = self.base.index(address), self.target.index(mapped)
        if b < 0 or b + count > len(self.target.words):
            return False
        for k in range(count):
            base_target = branch_target(self.base.words[a + k], address + 4 * k)
            if base_target is None:
                continue
            expected = self._reliable(base_target)
            if expected is not None and branch_target(self.target.words[b + k], mapped + 4 * k) != expected:
                return False
        return True

    def _normalized_bytes(self, shaped: bool = False) -> tuple[bytes, bytes]:
        """Normalized images as bytes; `shaped` also masks D-form displacements
        so code survives field offsets that moved when classes grew."""
        key = "_shaped_bytes" if shaped else "_bytes"
        if not hasattr(self, key):
            a, b = self.base.norm, self.target.norm
            if shaped:
                a, b = shape(a), shape(b)
            setattr(self, key, (struct.pack(f">{len(a)}I", *a), struct.pack(f">{len(b)}I", *b)))
        return getattr(self, key)

    def _context(self, address: int, shaped: bool = False) -> int | None:
        base_bytes, target_bytes = self._normalized_bytes(shaped)
        index = self.base.index(address)
        hits = set()
        # Every window covers the address and at least three instructions after
        # it; a window ending before the address can match a reordered
        # neighbour's tail and land on an unrelated function.
        for before, after in ((8, 16), (16, 8), (0, 24), (4, 8), (8, 4), (16, 16)):
            if index - before < 0 or index + after > len(self.base.norm):
                continue
            pattern = base_bytes[(index - before) * 4:(index + after) * 4]
            if len(_aligned_hits(base_bytes, pattern)) != 1:
                continue
            found = _aligned_hits(target_bytes, pattern)
            if len(found) == 1:
                candidate = self.target.load + found[0] + before * 4
                if self.branches_consistent(address - before * 4, candidate - before * 4, before + after):
                    hits.add(candidate)
        return hits.pop() if len(hits) == 1 else None

    def map(self, address: int, kind: str = "code", size: int = 4) -> tuple[int | None, str]:
        if kind == "data":
            if address in self.data:
                return self.data[address], "data"
            mapped = self._code_ref(address, 0, verify=False)
            if mapped is not None:
                return mapped, "data-ref"
            return None, "unmapped"
        start = self.base.containing(address)
        if start in self.exact:
            return self.exact[start] + (address - start), "exact"
        if start is not None and start not in self.anchored:
            self._pair_function(start)
        if start in self.anchored:
            mapped = self._alignment(start).get(address)
            if mapped is not None:
                return mapped, "aligned"
        if start is None and kind == "function":
            # Outside .pdata (vtable targets, thunks): runs of near-identical
            # thunks defeat context search, so prefer structural references.
            for method, finder in (("vtable", self._vtable), ("code-ref", self._code_ref)):
                mapped = finder(address, size)
                if mapped is not None:
                    return mapped, method
        if self.base.load <= address < self.base.load + len(self.base.data):
            mapped = self._context(address)
            if mapped is not None:
                return mapped, "context"
        mapped = self._neighbor(address, size)
        if mapped is not None:
            return mapped, "neighbor"
        mapped = self._vtable(address, size)
        if mapped is not None:
            return mapped, "vtable"
        if kind not in ("ref", "function"):
            mapped = self._code_ref(address, size)
            if mapped is not None:
                return mapped, "code-ref"
        if self.base.load <= address < self.base.load + len(self.base.data):
            mapped = self._context(address, shaped=True)
            if mapped is not None:
                return mapped, "shape-context"
        if address in self.data:
            return self.data[address], "data"
        return None, "unmapped"

    def _pair_function(self, start: int) -> None:
        """Pair a function reached only through data or address references."""
        busy = self.__dict__.setdefault("_busy", set())
        if start in busy:
            return
        busy.add(start)
        try:
            target = self._vtable(start, 16) or self._code_ref(start, 16)
        finally:
            busy.discard(start)
        if target is not None and target in self.target.functions and                 target not in self.exact.values() and target not in self.anchored.values():
            self.anchored[start] = target

    def _code_ref(self, address: int, size: int, verify: bool = True) -> int | None:
        """Follow lis/addi-style references to the address from mapped code."""
        if not hasattr(self, "_refs"):
            self._refs = collections.defaultdict(list)
            for start in self.base.starts:
                for k, target in absolute_refs(self.base, start, self.base.functions[start]).items():
                    self._refs[target].append(start + k * 4)
        candidates = set()
        for site in self._refs.get(address, ()):
            mapped_site, _ = self.map(site, "ref")
            if mapped_site is None:
                return None
            value = reference_at(self.target, mapped_site)
            if value is None:
                return None
            candidates.add(value)
        if len(candidates) != 1:
            return None
        candidate = candidates.pop()
        if not verify:
            return candidate
        a, b, n = self.base.index(address), self.target.index(candidate), max(size, 4) // 4
        # The referenced code may differ in displacements (for example a
        # vtable slot that moved when the class gained methods).
        if 0 <= b and shape(self.base.norm[a:a + n]) == shape(self.target.norm[b:b + n]):
            return candidate
        return None

    def _vtable(self, address: int, size: int) -> int | None:
        """Follow data slots that point at the address (vtables, callbacks).

        A slot is translated through the nearest preceding paired data address
        (for example a vtable whose address code loads with lis/addi). Every
        slot must yield the same v4 pointer, and the code there must match the
        normalized words of the requested range."""
        if not hasattr(self, "_data_keys"):
            self._data_keys = sorted(self.data)
        needle = address.to_bytes(4, "big")
        candidates = set()
        for slot in _aligned_hits(self.base.data, needle, limit=64):
            slot_va = self.base.load + slot
            i = bisect.bisect_right(self._data_keys, slot_va) - 1
            if i < 0 or slot_va - self._data_keys[i] > 0x1000:
                continue
            anchor = self._data_keys[i]
            t_slot = self.data[anchor] + (slot_va - anchor) - self.target.load
            if 0 <= t_slot <= len(self.target.data) - 4:
                candidates.add(int.from_bytes(self.target.data[t_slot:t_slot + 4], "big"))
        if len(candidates) != 1:
            return None
        candidate = candidates.pop()
        a, b, n = self.base.index(address), self.target.index(candidate), max(size, 4) // 4
        if 0 <= b and shape(self.base.norm[a:a + n]) == shape(self.target.norm[b:b + n]):
            return candidate
        return None

    def _neighbor(self, address: int, size: int) -> int | None:
        """Use the shift of the nearest exactly matched functions on either side.

        Accept a shift only if the normalized words from 16 bytes before to 16
        bytes after the requested range are identical at the shifted address,
        and exactly one candidate shift passes."""
        if not hasattr(self, "_exact_starts"):
            self._exact_starts = sorted(self.exact)
        i = bisect.bisect_right(self._exact_starts, address)
        shifts = set()
        for j in (i - 2, i - 1, i, i + 1):
            if 0 <= j < len(self._exact_starts):
                start = self._exact_starts[j]
                shifts.add(self.exact[start] - start)
        first, last = self.base.index(address) - 4, self.base.index(address + max(size, 4)) + 4
        if first < 0 or last > len(self.base.norm):
            return None
        window = self.base.norm[first:last]
        passing = []
        for shift in shifts:
            t_first = first + shift // 4
            if t_first >= 0 and self.target.norm[t_first:t_first + len(window)] == window and                     self.branches_consistent(address - 16, address - 16 + shift, len(window)):
                passing.append(address + shift)
        return passing[0] if len(passing) == 1 else None


def _aligned_hits(haystack: bytes, needle: bytes, limit: int = 2) -> list[int]:
    hits, position = [], haystack.find(needle)
    while position != -1 and len(hits) < limit:
        if position % 4 == 0:
            hits.append(position)
        position = haystack.find(needle, position + 1)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_image", type=Path)
    parser.add_argument("v4_image", type=Path)
    parser.add_argument("--load", type=lambda v: int(v, 0), default=LOAD)
    parser.add_argument("--addresses", type=Path, help="JSON list of {address, kind}")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mapper = Mapper(Image(args.base_image.read_bytes(), args.load), Image(args.v4_image.read_bytes(), args.load))
    result = {"functions": {"base": len(mapper.base.starts), "v4": len(mapper.target.starts),
                            "exact": len(mapper.exact), "anchored": len(mapper.anchored)},
              "data_pairs": len(mapper.data), "addresses": {}}
    if args.addresses:
        for entry in json.loads(args.addresses.read_text(encoding="utf-8")):
            address = int(entry["address"], 16) if isinstance(entry["address"], str) else entry["address"]
            mapped, method = mapper.map(address, entry.get("kind", "code"))
            result["addresses"][f"{address:08X}"] = {"v4": f"{mapped:08X}" if mapped is not None else None,
                                                     "method": method}
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
