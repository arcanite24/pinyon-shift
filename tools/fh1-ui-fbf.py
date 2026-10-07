"""Inspect FH1 UI4 native objects and check a BGF against its FBF companion.

The retail pause FBF uses version 1008. Its reader is sub_82E6E1D8:
the header is version/object count, each record is type/ID/name/payload,
and sub_82E605F8 consumes the trailing geometry and GPU data. Object IDs
are independent of the BGF string-table indexes. Inspection is read-only;
--clone-row writes three new experimental companions without changing inputs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys


class FbfError(ValueError):
    pass


def parse(data: bytes) -> dict:
    cursor = 0

    def take(size):
        nonlocal cursor
        if size < 0 or cursor + size > len(data):
            raise FbfError(f"truncated FBF at {cursor}: needs {size} bytes")
        result = data[cursor:cursor + size]
        cursor += size
        return result

    def word():
        return struct.unpack(">I", take(4))[0]

    def string():
        return take(word()).decode("utf-8", errors="replace")

    version, count = word(), word()
    if version != 1008:
        raise FbfError(f"unsupported FBF version {version}")
    if count > len(data) // 12:
        raise FbfError("object count exceeds the available record headers")
    records = []
    ids = set()
    for index in range(count):
        start = cursor
        kind, identity, name = word(), word(), string()
        body = cursor
        if identity in ids:
            raise FbfError(f"duplicate native object ID {identity}")
        ids.add(identity)
        if kind == 1:
            # sub_82E6AE50: three variable strings and frame/appearance data.
            take(4)
            string()
            string()
            take(8)
            string()
            take(4 + 7 * 4 + 1 + 4)
            if take(1) != b"\0":
                # Packed extension: three booleans and fourteen words (59 B).
                take(59)
        elif kind in (2, 3, 4, 5, 6):
            take({2: 64, 3: 24, 4: 8, 5: 104, 6: 104}[kind])
        elif kind == 7:
            # sub_82E6B658: material owner, texture name, matrix and fields.
            take(4)
            string()
            take(64 + 13 * 4)
        elif kind != 0:
            raise FbfError(f"unsupported FBF object type {kind}")
        records.append(dict(index=index, kind=kind, identity=identity,
                            name=name, start=start, body=body, end=cursor))
    tail = cursor
    geometry, extra, gpu = word(), word(), word()
    take(geometry * 96 + extra)
    take(gpu)
    if cursor != len(data):
        raise FbfError(f"unconsumed FBF bytes at {cursor}")
    return dict(version=version, records=records, tail=tail,
                geometry_objects=geometry, extra_geometry_bytes=extra,
                gpu_bytes=gpu)


def missing_objects(items, records) -> list[dict]:
    ids = {record["identity"] for record in records}
    return [dict(item=index, kind=item.kind, native_object_id=item.value)
            for index, item in enumerate(items)
            if item.kind in (1, 4, 5, 6, 7) and item.value not in ids]


def parse_bsg(data: bytes) -> dict:
    """Inspect the retail pause scene graph (82F27210 through 82F279C8).

    Nodes have 96 packed bytes; their parents are node indexes. The final
    five-byte records form a separate pool, not the FBF native-object table.
    """
    if len(data) < 48:
        raise FbfError("truncated BSG header")
    if (data[:4] != b"\x01\x04\0\0" or data[8:16] != b"FGBkranA"
            or struct.unpack_from(">I", data, 4)[0] != 24
            or struct.unpack_from(">I", data, 16)[0] != 2):
        raise FbfError("unsupported BSG header")
    declared, nodes, pool, node_bytes = struct.unpack_from(">4I", data, 32)
    if declared != 8 or node_bytes != nodes * 96:
        raise FbfError("BSG node counts do not match declared bytes")
    tail = 48 + node_bytes
    if tail + 4 > len(data):
        raise FbfError("truncated BSG nodes")
    pool_bytes = struct.unpack_from(">I", data, tail)[0]
    if pool_bytes != pool * 5 or tail + 4 + pool_bytes != len(data):
        raise FbfError("BSG pool count or file length mismatch")
    records = []
    for index in range(nodes):
        start = 48 + index * 96
        parent, identity = struct.unpack_from(">2I", data, start)
        if parent != 0xFFFFFFFF and parent >= index:
            raise FbfError(f"BSG node {index} has an unavailable parent {parent}")
        records.append(dict(index=index, parent=parent, identity=identity,
                            start=start, end=start + 96))
    pool_records = [dict(identity=struct.unpack_from(">I", data, offset)[0],
                         kind=data[offset + 4], start=offset, end=offset + 5)
                    for offset in range(tail + 4, len(data), 5)]
    ids = [node["identity"] for node in records + pool_records]
    if len(ids) != len(set(ids)):
        raise FbfError("duplicate BSG native object ID")
    return dict(nodes=records, pool=pool_records, pool_records=pool, pool_bytes=pool_bytes)


def clone_objects(fbf_data: bytes, bsg_data: bytes, object_ids) -> tuple[bytes, bytes, dict[int, int]]:
    """Clone owned native objects, preserving immutable geometry/GPU payloads.

    Materials and textures receive independent owners. BSG parents inside the
    copied subtree are relocated; the root keeps its existing external parent.
    """
    native, graph = parse(fbf_data), parse_bsg(bsg_data)
    ids = set(object_ids)
    records = {record["identity"]: record for record in native["records"]}
    graph_ids = {record["identity"] for record in graph["nodes"] + graph["pool"]}
    if graph_ids != records.keys():
        raise FbfError("FBF and BSG native object tables disagree")
    if not ids or not ids <= records.keys():
        raise FbfError("clone references missing native objects")
    mapping = {identity: max(records) + 1 + index
               for index, identity in enumerate(sorted(ids))}
    copies = []
    for record in native["records"]:
        if record["identity"] not in ids:
            continue
        copy = bytearray(fbf_data[record["start"]:record["end"]])
        struct.pack_into(">I", copy, 4, mapping[record["identity"]])
        if record["kind"] in (5, 7):
            offset = record["body"] - record["start"] + (68 if record["kind"] == 5 else 0)
            owner = struct.unpack_from(">I", copy, offset)[0]
            if owner not in mapping:
                raise FbfError(f"cloned object {record['identity']} has external mutable owner {owner}")
            struct.pack_into(">I", copy, offset, mapping[owner])
        copies.append(bytes(copy))
    fbf_out = bytearray(fbf_data[:native["tail"]] + b"".join(copies) + fbf_data[native["tail"]:])
    struct.pack_into(">I", fbf_out, 4, len(records) + len(copies))

    nodes = [node for node in graph["nodes"] if node["identity"] in ids]
    node_map = {node["index"]: len(graph["nodes"]) + index for index, node in enumerate(nodes)}
    node_copies = []
    found = {node["identity"] for node in nodes}
    for node in nodes:
        copy = bytearray(bsg_data[node["start"]:node["end"]])
        struct.pack_into(">2I", copy, 0, node_map.get(node["parent"], node["parent"]), mapping[node["identity"]])
        node_copies.append(bytes(copy))
    tail = 48 + len(graph["nodes"]) * 96
    pool_copies = []
    for offset in range(tail + 4, len(bsg_data), 5):
        identity = struct.unpack_from(">I", bsg_data, offset)[0]
        if identity in ids:
            found.add(identity)
            pool_copies.append(struct.pack(">I", mapping[identity]) + bsg_data[offset + 4:offset + 5])
    if found != ids or len(nodes) + len(pool_copies) != len(ids):
        raise FbfError("clone object IDs do not have unique BSG owners")
    pool = bsg_data[tail + 4:] + b"".join(pool_copies)
    bsg_out = bytearray(bsg_data[:tail] + b"".join(node_copies) + struct.pack(">I", len(pool)) + pool)
    struct.pack_into(">3I", bsg_out, 36, len(graph["nodes"]) + len(nodes),
                     graph["pool_records"] + len(pool_copies),
                     (len(graph["nodes"]) + len(nodes)) * 96)
    parse(bytes(fbf_out))
    parse_bsg(bytes(bsg_out))
    return bytes(fbf_out), bytes(bsg_out), mapping


def position_pause_clone(source: bytes, cloned: bytes, root_ids, clone_id: int) -> bytes:
    """Place the eighth row using the seven authored rows' local Y spacing."""
    roots = {node['identity']: node for node in parse_bsg(source)['nodes']}
    if len(root_ids) != 7 or any(identity not in roots for identity in root_ids):
        raise FbfError('pause layout requires seven authored row roots')
    positions = [struct.unpack_from('>f', source, roots[identity]['start'] + 16)[0]
                 for identity in root_ids]
    step = positions[1] - positions[0]
    if not all(math.isfinite(value) for value in positions) or not step or any(
            not math.isclose(value, positions[0] + index * step, abs_tol=0.001)
            for index, value in enumerate(positions)):
        raise FbfError('pause row spacing is not a finite, regular layout')
    nodes = {node['identity']: node for node in parse_bsg(cloned)['nodes']}
    if clone_id not in nodes or clone_id in roots:
        raise FbfError('pause clone root is absent or aliases an authored root')
    output = bytearray(cloned)
    struct.pack_into('>f', output, nodes[clone_id]['start'] + 16,
                     positions[0] + 7 * step)
    return bytes(output)


def name_pause_clone(data: bytes, clone_id: int) -> bytes:
    """Match the independent native row's name to the BGF Button7 wrapper."""
    records = parse(data)['records']
    record = next((row for row in records if row['identity'] == clone_id), None)
    if (record is None or record['kind'] != 0 or
            record['name'] not in {f'Button{index}' for index in range(7)} or
            any(row['name'] == 'Button7' for row in records)):
        raise FbfError('pause clone requires a unique Button7 native root')
    output = bytearray(data)
    start = record['start'] + 12
    output[start:start + 7] = b'Button7'
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fbf", type=Path)
    parser.add_argument("--bgf", type=Path)
    parser.add_argument("--bsg", type=Path, help="also inspect the scene graph companion")
    parser.add_argument("--clone-row", type=int, help="clone a pause row across BGF/FBF/BSG")
    parser.add_argument("--output-dir", type=Path, help="new companion files; existing files are refused")
    args = parser.parse_args()
    try:
        result = parse(args.fbf.read_bytes())
        if args.bsg:
            result["scene_graph"] = parse_bsg(args.bsg.read_bytes())
        if args.bgf:
            spec = importlib.util.spec_from_file_location(
                "scene_insert", Path(__file__).with_name("fh1-ui-scene-insert.py"))
            scene = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = scene
            spec.loader.exec_module(scene)
            items = scene.find_pause_section(args.bgf.read_bytes()).items
            result["missing_native_objects"] = missing_objects(items, result["records"])
        if args.clone_row is not None:
            if not args.bgf or not args.bsg or not args.output_dir:
                raise FbfError("--clone-row requires --bgf, --bsg and --output-dir")
            if result["missing_native_objects"]:
                raise FbfError("source BGF references absent native objects")
            bgf_data = args.bgf.read_bytes()
            section = scene.find_pause_section(bgf_data)
            pairs = scene.pause_row_pairs(section)
            if not 0 <= args.clone_row < len(pairs):
                raise FbfError("row index is outside the authored rows")
            first, last = scene.row_subtree(section, pairs[args.clone_row][1])
            object_ids = {item.value for item in section.items[first:last + 1]
                          if item.kind in (1, 4, 5, 6, 7)}
            fbf_out, bsg_out, mapping = clone_objects(
                args.fbf.read_bytes(), args.bsg.read_bytes(), object_ids)
            fbf_out = name_pause_clone(fbf_out, mapping[pairs[args.clone_row][1].value])
            bsg_out = position_pause_clone(args.bsg.read_bytes(), bsg_out,
                [wrapper.value for _, wrapper, _ in pairs], mapping[pairs[args.clone_row][1].value])
            bgf_out, summary = scene.encode_subtree(bgf_data, args.clone_row, mapping)
            missing = missing_objects(scene.find_pause_section(bgf_out).items, parse(fbf_out)["records"])
            if missing:
                raise FbfError(f"clone still has missing native objects: {missing}")
            outputs = {"bgf": bgf_out, "fbf": fbf_out, "bsg": bsg_out}
            paths = {suffix: args.output_dir / (args.bgf.stem + "." + suffix) for suffix in outputs}
            if any(path.exists() for path in paths.values()):
                raise FbfError("output companion files already exist")
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for suffix, data in outputs.items():
                with paths[suffix].open("xb") as stream:
                    stream.write(data)
            result = dict(clone=summary, outputs={key: str(path) for key, path in paths.items()},
                          missing_native_objects=missing, native_insertion_qualified=False)
        print(json.dumps(result, indent=2))
        return 1 if result.get("missing_native_objects") else 0
    except (FbfError, OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
