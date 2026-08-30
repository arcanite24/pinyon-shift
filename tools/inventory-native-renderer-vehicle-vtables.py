#!/usr/bin/env python3
"""Resolve captured vehicle-owner vtables into generated title methods."""

import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-vehicle-vtable-inventory.v1"
FUNCTION_PREFIX = "DEFINE_REX_FUNC(sub_"
DIRECT_CALL = re.compile(r"\bsub_([0-9A-Fa-f]{8})\(ctx, base\);")
TAIL_CALL = re.compile(r"REX_TAIL_CALL\(([^)]+)\)")
TAIL_CALL_ADDRESS = re.compile(r"sub_([0-9A-Fa-f]{8})")
DEFAULT_CALLGRAPH_DEPTH = 12
DEFAULT_CALLGRAPH_NODE_LIMIT = 4096


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_hex(value, width, field, allow_zero=False):
    text = str(value).upper()
    if len(text) != width:
        raise ValueError(f"invalid {field}")
    try:
        parsed = int(text, 16)
    except ValueError as error:
        raise ValueError(f"invalid {field}") from error
    if not allow_zero and not parsed:
        raise ValueError(f"zero {field}")
    return text, parsed


def extract_function(source, address):
    marker = f"{FUNCTION_PREFIX}{address}) {{"
    start = source.find(marker)
    if start < 0:
        return None
    end = source.find("\nDEFINE_REX_FUNC(", start + len(marker))
    if end < 0:
        end = len(source)
    return source[start:end]


def resolve_method(address, assignments, generated_root, cache):
    partition = assignments.get(address)
    if partition is None:
        return {
            "address": address,
            "resolution": "not_in_codegen_partition",
            "render_method_candidate_only": True,
        }
    source_path = generated_root / f"pinyon_shift_recomp.{partition}.cpp"
    if source_path not in cache:
        try:
            cache[source_path] = source_path.read_text(encoding="utf-8")
        except OSError:
            cache[source_path] = None
    source = cache[source_path]
    if source is None:
        return {
            "address": address,
            "partition": partition,
            "source": str(source_path),
            "resolution": "generated_source_missing",
            "render_method_candidate_only": True,
        }
    body = extract_function(source, address)
    if body is None:
        return {
            "address": address,
            "partition": partition,
            "source": str(source_path),
            "resolution": "function_body_missing",
            "render_method_candidate_only": True,
        }
    direct_callees = sorted({value.upper() for value in DIRECT_CALL.findall(body)})
    tail_callees = sorted({value.strip() for value in TAIL_CALL.findall(body)})
    return {
        "address": address,
        "partition": partition,
        "source": str(source_path),
        "resolution": "generated_function",
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest().upper(),
        "instruction_comments": body.count("\n\t// "),
        "direct_callees": direct_callees,
        "indirect_calls": body.count("REX_CALL_INDIRECT_FUNC"),
        "tail_callees": tail_callees,
        "native_hook_mentions": sorted(
            set(re.findall(r"\bPinyonShift[A-Za-z0-9_]+", body))
        ),
        "render_method_candidate_only": True,
    }


def trace_reachable_hooks(root, resolve, max_depth, node_limit):
    queue = collections.deque([(root, [root], 0)])
    visited = set()
    hook_paths = []
    unresolved = set()
    depth_limited = False
    node_limited = False
    while queue:
        address, path, depth = queue.popleft()
        if address in visited:
            continue
        if len(visited) >= node_limit:
            node_limited = True
            break
        visited.add(address)
        method = resolve(address)
        if method.get("resolution") != "generated_function":
            unresolved.add(address)
            continue
        hooks = method.get("native_hook_mentions", [])
        if hooks:
            hook_paths.append(
                {
                    "target_address": address,
                    "depth": depth,
                    "path": path,
                    "native_hook_mentions": hooks,
                }
            )
        callees = list(method.get("direct_callees", []))
        for tail in method.get("tail_callees", []):
            match = TAIL_CALL_ADDRESS.fullmatch(tail)
            if match:
                callees.append(match.group(1).upper())
        callees = sorted(set(callees))
        if depth >= max_depth:
            if callees:
                depth_limited = True
            continue
        for callee in callees:
            if callee not in visited:
                queue.append((callee, path + [callee], depth + 1))
    hook_paths.sort(
        key=lambda item: (item["depth"], item["target_address"], item["path"])
    )
    return {
        "reachable_generated_functions": len(visited) - len(unresolved),
        "reachable_unresolved_functions": sorted(unresolved),
        "reachable_hook_paths": hook_paths,
        "closest_native_hook_depth": (
            hook_paths[0]["depth"] if hook_paths else None
        ),
        "callgraph_depth_limit": max_depth,
        "callgraph_node_limit": node_limit,
        "callgraph_depth_limited": depth_limited,
        "callgraph_node_limited": node_limited,
        "static_callgraph_candidate_only": True,
    }


def build(
    report,
    partition_document,
    generated_root,
    callgraph_depth=DEFAULT_CALLGRAPH_DEPTH,
    callgraph_node_limit=DEFAULT_CALLGRAPH_NODE_LIMIT,
):
    if report.get("schema") != "pinyon-shift.native-renderer-vehicle-pose.v1":
        raise ValueError("unexpected vehicle-pose report schema")
    if report.get("status") != "complete":
        raise ValueError("vehicle-pose report is not complete")
    qualification = report.get("qualification", {})
    if not qualification.get("vehicle_owner_class_seed_proved"):
        raise ValueError("vehicle owner class seed is not qualified")
    if qualification.get("player_vehicle_identity_proved"):
        raise ValueError("vehicle report unexpectedly claims player identity")
    owner_classes = report.get("owner_classes")
    if not isinstance(owner_classes, list) or not owner_classes:
        raise ValueError("vehicle report has no owner classes")
    assignments_raw = partition_document.get("assignments")
    if not isinstance(assignments_raw, dict):
        raise ValueError("codegen partition has no assignments")
    assignments = {str(key).upper(): value for key, value in assignments_raw.items()}
    if callgraph_depth < 0:
        raise ValueError("callgraph depth must be non-negative")
    if callgraph_node_limit < 1:
        raise ValueError("callgraph node limit must be positive")

    method_slots = {}
    classes = []
    for owner_class in owner_classes:
        vtable, _ = validate_hex(
            owner_class.get("owner_vtable"), 8, "owner_vtable"
        )
        vtable_hash, _ = validate_hex(
            owner_class.get("owner_vtable_hash"), 16, "owner_vtable_hash"
        )
        methods = owner_class.get("owner_vtable_methods")
        if not isinstance(methods, list) or len(methods) != 32:
            raise ValueError("owner vtable must contain 32 method slots")
        normalized = []
        for slot, method in enumerate(methods):
            address, parsed = validate_hex(
                method, 8, "owner_vtable_method", allow_zero=True
            )
            normalized.append(address)
            if parsed:
                method_slots.setdefault(address, []).append(
                    {"owner_vtable": vtable, "slot": slot}
                )
        classes.append(
            {
                "owner_vtable": vtable,
                "owner_vtable_hash": vtable_hash,
                "identity_count": int(owner_class.get("identity_count", 0)),
                "method_slots": normalized,
            }
        )

    correlations = {}
    for correlation in report.get("method_correlations", []):
        address, parsed = validate_hex(
            correlation.get("method_address"),
            8,
            "correlated_method_address",
        )
        if not parsed or address in correlations or address not in method_slots:
            raise ValueError("invalid correlated vehicle method")
        slot = int(correlation.get("vtable_slot", -1))
        if not any(owner["slot"] == slot for owner in method_slots[address]):
            raise ValueError("correlated vehicle method slot drifted")
        calls = int(correlation.get("calls", -1))
        matched_owner_calls = int(correlation.get("matched_owner_calls", -1))
        exits = int(correlation.get("exits", -1))
        direct_draw_origins = int(correlation.get("direct_draw_origins", -1))
        backend_draw_matches = int(correlation.get("backend_draw_matches", -1))
        proved = bool(
            correlation.get("vehicle_render_method_candidate_proved")
        )
        if (
            min(
                calls,
                matched_owner_calls,
                exits,
                direct_draw_origins,
                backend_draw_matches,
            )
            < 0
            or calls != exits
            or matched_owner_calls > calls
            or backend_draw_matches > direct_draw_origins
            or proved != (backend_draw_matches > 0)
        ):
            raise ValueError("correlated vehicle method accounting drifted")
        correlations[address] = {
            "vtable_slot": slot,
            "calls": calls,
            "matched_owner_calls": matched_owner_calls,
            "exits": exits,
            "direct_draw_origins": direct_draw_origins,
            "backend_draw_matches": backend_draw_matches,
            "vehicle_render_method_candidate_proved": proved,
            "vehicle_draw_identity_proved": False,
        }
    correlation_proved = any(
        item["vehicle_render_method_candidate_proved"]
        for item in correlations.values()
    )
    if bool(qualification.get("vehicle_render_method_candidate_proved")) != (
        correlation_proved
    ):
        raise ValueError("vehicle render-method candidate qualification drifted")

    cache = {}
    resolution_cache = {}

    def resolve(address):
        if address not in resolution_cache:
            resolution_cache[address] = resolve_method(
                address, assignments, generated_root, cache
            )
        return dict(resolution_cache[address])

    methods = []
    for address in sorted(method_slots):
        method = resolve(address)
        method["owners"] = sorted(
            method_slots[address], key=lambda item: (item["owner_vtable"], item["slot"])
        )
        if address in correlations:
            method["runtime_correlation"] = correlations[address]
        method.update(
            trace_reachable_hooks(
                address, resolve, callgraph_depth, callgraph_node_limit
            )
        )
        methods.append(method)
    component_dispatches = []
    for dispatch in report.get("indirect_targets", []):
        owner_method, _ = validate_hex(
            dispatch.get("method_address"), 8, "component_owner_method"
        )
        callsite, _ = validate_hex(
            dispatch.get("callsite_address"), 8, "component_callsite"
        )
        target, _ = validate_hex(
            dispatch.get("target_address"), 8, "component_target"
        )
        object_address, _ = validate_hex(
            dispatch.get("object_address"), 8, "component_object"
        )
        object_vtable, _ = validate_hex(
            dispatch.get("object_vtable"), 8, "component_object_vtable"
        )
        observations = int(dispatch.get("observations", -1))
        if owner_method not in method_slots or observations < 1:
            raise ValueError("invalid vehicle component dispatch")
        target_method = resolve(target)
        target_method.update(
            trace_reachable_hooks(
                target, resolve, callgraph_depth, callgraph_node_limit
            )
        )
        component_dispatches.append(
            {
                "owner_method_address": owner_method,
                "callsite_address": callsite,
                "target_address": target,
                "object_address": object_address,
                "object_vtable": object_vtable,
                "observations": observations,
                "first_frame": int(dispatch.get("first_frame", 0)),
                "last_frame": int(dispatch.get("last_frame", 0)),
                "target_method": target_method,
                "vehicle_component_dispatch_candidate_only": True,
            }
        )
    component_dispatches.sort(
        key=lambda item: (
            item["callsite_address"],
            item["target_address"],
            item["object_vtable"],
        )
    )
    unresolved_component_targets = sum(
        item["target_method"]["resolution"] != "generated_function"
        for item in component_dispatches
    )
    resolved = sum(item["resolution"] == "generated_function" for item in methods)
    unresolved = len(methods) - resolved
    return {
        "schema": SCHEMA,
        "source_vehicle_session": report.get("session"),
        "status": "complete",
        "owner_classes": classes,
        "methods": methods,
        "component_dispatches": component_dispatches,
        "totals": {
            "owner_classes": len(classes),
            "method_slots": len(classes) * 32,
            "unique_nonzero_methods": len(methods),
            "resolved_generated_methods": resolved,
            "unresolved_methods": unresolved,
            "methods_reaching_native_hooks": sum(
                bool(item["reachable_hook_paths"]) for item in methods
            ),
            "callgraphs_depth_limited": sum(
                item["callgraph_depth_limited"] for item in methods
            ),
            "callgraphs_node_limited": sum(
                item["callgraph_node_limited"] for item in methods
            ),
            "runtime_correlated_methods": len(correlations),
            "runtime_proved_candidates": sum(
                item["vehicle_render_method_candidate_proved"]
                for item in correlations.values()
            ),
            "component_dispatch_targets": len(component_dispatches),
            "unresolved_component_dispatch_targets": (
                unresolved_component_targets
            ),
        },
        "qualification": {
            "owner_vtable_inventory_proved": True,
            "generated_method_resolution_complete": unresolved == 0,
            "vehicle_render_method_candidate_proved": correlation_proved,
            "vehicle_component_dispatch_seed_proved": (
                bool(component_dispatches)
                and unresolved_component_targets == 0
            ),
            "vehicle_render_method_identity_proved": False,
            "player_vehicle_identity_proved": False,
            "native_vehicle_rendering_admitted": False,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("--partition", required=True, type=pathlib.Path)
    parser.add_argument("--generated-root", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument(
        "--callgraph-depth", type=int, default=DEFAULT_CALLGRAPH_DEPTH
    )
    parser.add_argument(
        "--callgraph-node-limit", type=int, default=DEFAULT_CALLGRAPH_NODE_LIMIT
    )
    args = parser.parse_args(argv)
    try:
        document = build(
            load_json(args.report),
            load_json(args.partition),
            args.generated_root,
            args.callgraph_depth,
            args.callgraph_node_limit,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vehicle vtable inventory failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
