#!/usr/bin/env python3
"""Build a bounded NR-02 geometry contract from candidate census metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SELECTION_SCHEMA = "pinyon-shift.native-renderer-candidate-selection.v1"
CENSUS_SCHEMA = "pinyon-shift.native-renderer-census.v1"
SCHEMA = "pinyon-shift.native-geometry-contract.v1"
PHYSICAL_MASK = 0x1FFFFFFF
VERTEX_INDEX_MASK = 0xFFFFFF

VERTEX_FORMATS = {
    6: ("8_8_8_8", 4, 4, "packed_integer"),
    7: ("2_10_10_10", 4, 4, "packed_integer"),
    16: ("10_11_11", 3, 4, "packed_integer"),
    17: ("11_11_10", 3, 4, "packed_integer"),
    25: ("16_16", 2, 4, "packed_integer"),
    26: ("16_16_16_16", 4, 8, "packed_integer"),
    31: ("16_16_FLOAT", 2, 4, "float"),
    32: ("16_16_16_16_FLOAT", 4, 8, "float"),
    33: ("32", 1, 4, "integer"),
    34: ("32_32", 2, 8, "integer"),
    35: ("32_32_32_32", 4, 16, "integer"),
    36: ("32_FLOAT", 1, 4, "float"),
    37: ("32_32_FLOAT", 2, 8, "float"),
    38: ("32_32_32_32_FLOAT", 4, 16, "float"),
    57: ("32_32_32_FLOAT", 3, 12, "float"),
}
INDEX_FORMATS = {
    0: ("uint16", 2),
    1: ("uint32", 4),
}
INDEX_ENDIANNESS = {
    0: "none",
    1: "8in16",
    2: "8in32",
    3: "16in32",
}
VERTEX_ENDIANNESS = {
    **INDEX_ENDIANNESS,
    4: "8in64",
    5: "8in128",
}
STORAGE_TARGETS = {
    0: "none",
    1: "register",
    2: "interpolator",
    3: "position",
    4: "point_size_edge_flag_kill_vertex",
    5: "export_address",
    6: "export_data",
    7: "color",
    8: "depth",
}
SWIZZLE_SOURCES = ("x", "y", "z", "w", "0", "1")


def needed_vertex_words(data_format: int, used_components: int) -> int:
    if data_format in (6, 7):
        return 0x1 if used_components else 0
    if data_format in (16, 17):
        return 0x1 if used_components & 0x7 else 0
    if data_format in (25, 31):
        return 0x1 if used_components & 0x3 else 0
    if data_format in (26, 32):
        return (0x1 if used_components & 0x3 else 0) | (
            0x2 if used_components & 0xC else 0
        )
    if data_format in (33, 36):
        return used_components & 0x1
    if data_format in (34, 37):
        return used_components & 0x3
    if data_format in (35, 38):
        return used_components & 0xF
    if data_format == 57:
        return used_components & 0x7
    raise ValueError(f"unsupported Xenos vertex format {data_format}")


def parse_state(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"candidate has no {field}")
    result: dict[str, int] = {}
    for item in value.split(";"):
        key, separator, raw = item.partition("=")
        if not separator or not key or not raw:
            raise ValueError(f"candidate has invalid {field}: {value!r}")
        result[key] = int(raw, 0)
    return result


def parse_fetches(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, str) or not value:
        raise ValueError("candidate has no vertex fetch metadata")
    fetches = []
    for item in value.split(";"):
        fields = item.split(":")
        if len(fields) != 5:
            raise ValueError(f"invalid vertex fetch metadata: {item!r}")
        fetch_constant, address, size, stride_words, endianness = fields
        fetches.append(
            {
                "fetch_constant": int(fetch_constant),
                "guest_address": int(address, 16),
                "size_bytes": int(size),
                "stride_words": int(stride_words),
                "endianness": int(endianness),
            }
        )
    return fetches


def parse_attributes(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, str) or not value:
        raise ValueError("candidate has no vertex attribute metadata")
    names = (
        "binding_index",
        "fetch_constant",
        "offset_words",
        "stride_words",
        "data_format",
        "fetch_word_mask",
        "exp_adjust",
        "signed_rf_mode",
        "result_storage_target",
        "result_storage_index",
        "result_write_mask",
        "result_components",
        "flags",
    )
    hexadecimal = {
        "fetch_word_mask",
        "result_write_mask",
        "result_components",
        "flags",
    }
    attributes = []
    for item in value.split(";"):
        fields = item.split(":")
        if len(fields) != len(names):
            raise ValueError(f"invalid vertex attribute metadata: {item!r}")
        attributes.append(
            {
                name: int(raw, 16 if name in hexadecimal else 10)
                for name, raw in zip(names, fields)
            }
        )
    return attributes


def select_candidate(document: dict[str, Any], signature: str | None) -> dict[str, Any]:
    if document.get("schema") != SELECTION_SCHEMA:
        raise ValueError(f"unsupported selection schema: {document.get('schema')}")
    candidates = document.get("candidates", [])
    if signature is not None:
        candidates = [item for item in candidates if item.get("signature") == signature]
    if len(candidates) != 1:
        raise ValueError("geometry planning requires exactly one selected candidate")
    return candidates[0]


def build(
    document: dict[str, Any],
    signature: str | None = None,
    index_censuses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidate = select_candidate(document, signature)
    if int(candidate.get("vertex_binding_count", 0)) != 1:
        raise ValueError("initial geometry contract requires exactly one vertex binding")
    fetches = parse_fetches(candidate.get("vertex_fetches"))
    if len(fetches) != 1:
        raise ValueError("initial geometry contract requires one bounded vertex fetch")
    attributes = parse_attributes(candidate.get("vertex_attributes"))
    if len(attributes) != int(candidate.get("vertex_attribute_count", 0)):
        raise ValueError("vertex attribute metadata count does not match the candidate")

    fetch = fetches[0]
    if fetch["size_bytes"] <= 0 or fetch["stride_words"] <= 0:
        raise ValueError("vertex fetch size and stride must be positive")
    if fetch["endianness"] not in VERTEX_ENDIANNESS:
        raise ValueError(
            f"unsupported Xenos vertex endianness {fetch['endianness']}"
        )
    stride_bytes = fetch["stride_words"] * 4
    maximum_extent = 0
    for attribute in attributes:
        if attribute["fetch_constant"] != fetch["fetch_constant"]:
            raise ValueError("vertex attribute references an unbounded fetch constant")
        if attribute["offset_words"] < 0:
            raise ValueError("negative vertex attribute offsets are not bounded")
        if attribute["stride_words"] != fetch["stride_words"]:
            raise ValueError("vertex attribute and fetch strides disagree")
        if attribute["fetch_word_mask"] <= 0:
            raise ValueError("vertex attribute has an empty fetch word mask")
        format_info = VERTEX_FORMATS.get(attribute["data_format"])
        if format_info is None:
            raise ValueError(
                f"unsupported Xenos vertex format {attribute['data_format']}"
            )
        format_name, component_count, storage_bytes, number_class = format_info
        storage_target = STORAGE_TARGETS.get(attribute["result_storage_target"])
        if storage_target is None:
            raise ValueError(
                "unsupported shader result storage target "
                f"{attribute['result_storage_target']}"
            )
        swizzle_codes = [
            (attribute["result_components"] >> (component * 3)) & 0x7
            for component in range(4)
        ]
        if any(code >= len(SWIZZLE_SOURCES) for code in swizzle_codes):
            raise ValueError("vertex attribute has an invalid result swizzle")
        used_components = 0
        for output_component, source_component in enumerate(swizzle_codes):
            if (
                attribute["result_write_mask"] & (1 << output_component)
                and source_component < 4
            ):
                used_components |= 1 << source_component
        expected_word_mask = needed_vertex_words(
            attribute["data_format"], used_components
        )
        if attribute["fetch_word_mask"] != expected_word_mask:
            raise ValueError(
                "vertex attribute fetch word mask disagrees with its format "
                "and result swizzle"
            )
        extent = (attribute["offset_words"] + attribute["fetch_word_mask"].bit_length()) * 4
        if extent > stride_bytes:
            raise ValueError("vertex attribute extends beyond its binding stride")
        attribute["extent_bytes"] = extent
        attribute["format_name"] = format_name
        attribute["component_count"] = component_count
        attribute["storage_bytes"] = storage_bytes
        attribute["number_class"] = number_class
        attribute["result_storage_target_name"] = storage_target
        attribute["result_write_components"] = "".join(
            component
            for index, component in enumerate("xyzw")
            if attribute["result_write_mask"] & (1 << index)
        )
        attribute["result_swizzle"] = "".join(
            SWIZZLE_SOURCES[code] for code in swizzle_codes
        )
        attribute["used_source_components"] = "".join(
            component
            for index, component in enumerate("xyzw")
            if used_components & (1 << index)
        )
        attribute["mini_fetch"] = bool(attribute["flags"] & 0x1)
        attribute["predicated"] = bool(attribute["flags"] & 0x2)
        attribute["predicate_condition"] = bool(attribute["flags"] & 0x4)
        attribute["index_rounded"] = bool(attribute["flags"] & 0x8)
        attribute["signed"] = bool(attribute["flags"] & 0x10)
        attribute["integer"] = bool(attribute["flags"] & 0x20)
        maximum_extent = max(maximum_extent, extent)

    normalized_address = fetch["guest_address"] & PHYSICAL_MASK
    if normalized_address + fetch["size_bytes"] > PHYSICAL_MASK + 1:
        raise ValueError("normalized vertex fetch crosses the physical aperture")

    index_range = parse_state(candidate.get("vertex_index_range"), "vertex_index_range")
    index_state = parse_state(candidate.get("index_state"), "index_state")
    index_format = index_state.get("format")
    index_endianness = index_state.get("endianness")
    if index_format not in INDEX_FORMATS:
        raise ValueError(f"unsupported Xenos index format {index_format}")
    if index_endianness not in INDEX_ENDIANNESS:
        raise ValueError(f"unsupported Xenos index endianness {index_endianness}")
    offset = index_range.get("offset")
    minimum = index_range.get("min")
    maximum = index_range.get("max")
    if offset is None or minimum is None or maximum is None or maximum < minimum:
        raise ValueError("candidate has an invalid vertex index range")

    indexed = bool(candidate.get("indexed"))
    index_count_max = int(candidate.get("index_count_max", 0))
    index_format_name, index_element_bytes = INDEX_FORMATS[index_format]
    index_buffer: dict[str, Any] | None = None
    bounds: dict[str, Any]
    if indexed:
        index_buffer_length = int(candidate.get("index_buffer_length_min", 0))
        required_index_bytes = index_count_max * index_element_bytes
        if index_buffer_length < required_index_bytes:
            raise ValueError(
                f"index fetch needs {required_index_bytes} bytes, "
                f"has {index_buffer_length}"
            )
        raw_index_address = candidate.get("index_buffer_address")
        if not isinstance(raw_index_address, str) or not raw_index_address:
            raise ValueError("indexed candidate has no index buffer address")
        guest_index_address = int(raw_index_address, 16)
        physical_index_address = guest_index_address & PHYSICAL_MASK
        if physical_index_address + index_buffer_length > PHYSICAL_MASK + 1:
            raise ValueError("normalized index fetch crosses the physical aperture")
        index_buffer = {
            "guest_address": guest_index_address,
            "physical_address": physical_index_address,
            "available_bytes": index_buffer_length,
            "required_bytes_before_scan": required_index_bytes,
        }
        if not index_censuses:
            bounds = {
                "status": "requires_index_scan",
                "validated": False,
                "reason": "no bounded index-scan evidence was supplied",
            }
        else:
            if len(index_censuses) < 2:
                raise ValueError("indexed qualification requires two scan captures")
            scans = []
            for census in index_censuses:
                if census.get("schema") != CENSUS_SCHEMA:
                    raise ValueError("unsupported index census schema")
                matching = [
                    scan
                    for scan in census.get("index_scans", [])
                    if scan.get("signature") == candidate.get("signature")
                    and scan.get("status") == "scanned"
                ]
                if len(matching) != 1:
                    raise ValueError(
                        "each index census must contain one successful candidate scan"
                    )
                scans.append(matching[0])
            for scan in scans:
                scan_count = int(scan.get("index_count", 0))
                scan_bytes = int(scan.get("bytes_read", 0))
                scan_length = int(scan.get("index_buffer_length", 0))
                scan_address = int(str(scan.get("index_buffer_address", "0")), 16)
                if scan_count < int(candidate.get("index_count_min", 0)) or (
                    scan_count > index_count_max
                ):
                    raise ValueError("index scan count is outside candidate observations")
                if int(scan.get("index_format", -1)) != index_format or int(
                    scan.get("index_endianness", -1)
                ) != index_endianness:
                    raise ValueError("index scan state disagrees with the candidate")
                if scan_bytes != scan_count * index_element_bytes:
                    raise ValueError("index scan byte count is inconsistent")
                if scan_bytes > scan_length:
                    raise ValueError("index scan exceeded its observed allocation")
                scan_physical_address = scan_address & PHYSICAL_MASK
                if scan_physical_address + scan_bytes > PHYSICAL_MASK + 1:
                    raise ValueError("index scan crosses the physical aperture")
                effective_minimum = int(scan.get("effective_minimum", -1))
                effective_maximum = int(scan.get("effective_maximum", -1))
                if (
                    int(scan.get("non_reset_count", 0)) <= 0
                    or effective_minimum < minimum
                    or effective_maximum > maximum
                    or effective_maximum < effective_minimum
                ):
                    raise ValueError("index scan has invalid effective bounds")
                if int(scan.get("vertex_binding_size", 0)) != fetch["size_bytes"]:
                    raise ValueError("index scan vertex allocation changed")
            stable_fields = (
                "decoded_minimum",
                "decoded_maximum",
                "effective_minimum",
                "effective_maximum",
                "non_reset_count",
                "reset_count",
                "decoded_hash",
                "index_reset_enabled",
                "index_reset",
            )
            if any(
                scan.get(field) != scans[0].get(field)
                for scan in scans[1:]
                for field in stable_fields
            ):
                raise ValueError("index payload or reset state changed across captures")
            maximum_vertex = int(scans[0]["effective_maximum"])
            required_vertex_bytes = maximum_vertex * stride_bytes + maximum_extent
            if required_vertex_bytes > fetch["size_bytes"]:
                raise ValueError(
                    f"scanned vertex fetch needs {required_vertex_bytes} bytes, "
                    f"has {fetch['size_bytes']}"
                )
            bounds = {
                "status": "bounded_index_scan",
                "validated": True,
                "scan_captures": len(scans),
                "decoded_minimum": int(scans[0]["decoded_minimum"]),
                "decoded_maximum": int(scans[0]["decoded_maximum"]),
                "effective_minimum": int(scans[0]["effective_minimum"]),
                "effective_maximum": maximum_vertex,
                "non_reset_count": int(scans[0]["non_reset_count"]),
                "reset_count": int(scans[0]["reset_count"]),
                "decoded_hash": scans[0]["decoded_hash"],
                "maximum_attribute_extent_bytes": maximum_extent,
                "required_vertex_bytes": required_vertex_bytes,
                "available_vertex_bytes": fetch["size_bytes"],
            }
    else:
        if index_count_max < 0:
            raise ValueError("index count must not be negative")
        raw_last = index_count_max - 1 if index_count_max else None
        if raw_last is None:
            maximum_vertex = None
            required_bytes = 0
        else:
            adjusted = raw_last + offset
            if adjusted > VERTEX_INDEX_MASK:
                raise ValueError("24-bit vertex index wrap is outside the initial contract")
            maximum_vertex = min(max(adjusted & VERTEX_INDEX_MASK, minimum), maximum)
            required_bytes = maximum_vertex * stride_bytes + maximum_extent
        if required_bytes > fetch["size_bytes"]:
            raise ValueError(
                f"vertex fetch needs {required_bytes} bytes, has {fetch['size_bytes']}"
            )
        bounds = {
            "status": "bounded",
            "validated": True,
            "raw_last_vertex": raw_last,
            "maximum_vertex": maximum_vertex,
            "maximum_attribute_extent_bytes": maximum_extent,
            "required_bytes": required_bytes,
            "available_bytes": fetch["size_bytes"],
        }

    return {
        "schema": SCHEMA,
        "candidate_signature": candidate.get("signature"),
        "primitive": int(candidate.get("primitive", 0)),
        "indexed": indexed,
        "source_select": int(candidate.get("source_select", 0)),
        "index_count": {
            "minimum_observed": int(candidate.get("index_count_min", 0)),
            "maximum_observed": index_count_max,
        },
        "vertex_index_range": {
            "offset": offset,
            "minimum": minimum,
            "maximum": maximum,
            "mask": VERTEX_INDEX_MASK,
        },
        "index": {
            "format": index_format,
            "format_name": index_format_name,
            "element_bytes": index_element_bytes,
            "endianness": index_endianness,
            "endianness_name": INDEX_ENDIANNESS[index_endianness],
            "buffer": index_buffer,
        },
        "binding": {
            **fetch,
            "endianness_name": VERTEX_ENDIANNESS[fetch["endianness"]],
            "physical_address": normalized_address,
            "stride_bytes": stride_bytes,
        },
        "attributes": attributes,
        "bounds": bounds,
        "safety": {
            "guest_payload_read": indexed and bool(index_censuses),
            "guest_payload_scope": (
                "bounded_index_only" if indexed and index_censuses else "none"
            ),
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--signature")
    parser.add_argument("--index-census", nargs="+", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = json.loads(args.selection.read_text(encoding="utf-8"))
    index_censuses = (
        [json.loads(path.read_text(encoding="utf-8")) for path in args.index_census]
        if args.index_census
        else None
    )
    rendered = json.dumps(
        build(document, args.signature, index_censuses), indent=2
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
