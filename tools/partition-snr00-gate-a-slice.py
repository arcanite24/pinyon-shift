"""Partition a strict SNR-01 frame ledger by title-proved Gate A role."""

import collections
import hashlib
import json
from pathlib import Path
import sys


CANDIDATE = {
    "14020500/00030000/00010400/00000003",
    "14020500/000C0000/00010400/00000003",
}
CAR_SCALAR = {0x82443B98, 0x82443C40, 0x82444018}
SKID_SCALAR = {0x823FDDFC, 0x823FDE2C}
RETAINED_DIRECT = {0x823F59C8, 0x82401258, 0x82D07200,
                   0x82D0735C, 0x8244F070}
CAR_SCENE_LIST = {0x824399F0, 0x8243CE0C, 0x8241A2A4,
                  0x8244DD5C, 0x8244CBF4, 0x8244E2A8}


def role(draw: dict) -> str:
    if draw["target"] not in CANDIDATE:
        kind = draw["classification"]
        if kind == "view_owner":
            assert draw["owner"] and draw["scene_source_frame"] is not None
            assert 0 <= draw["view_call"] < 8
        elif kind == "out_of_view_scene":
            assert draw["view_call"] == 0 and draw["scene_source_frame"] is not None
        elif kind == "direct_root":
            if draw["title_packet_source_frame"] is None:
                assert draw["root_source_frame"] is not None
                return "outside_unattributed_direct"
            assert draw["title_packet_source_frame"] is not None
            assert 0 <= draw["title_packet_view_call"] < 8
        elif kind == "title_clear":
            assert draw["clear_producer_record"] is not None
        else:
            assert kind == "unmatched_indirect" and draw["no_attachment_write"]
        return "outside_candidate_targets"
    kind = draw["classification"]
    if kind == "view_owner":
        assert draw["view_call"] == 8 and draw["owner"]
        if draw["flush_caller_lr"] == 0x824170BC:
            return "selected_shared_track_procedural"
        assert draw["flush_caller_lr"] in CAR_SCENE_LIST
        return "selected_car_scene_list"
    if kind == "title_clear":
        assert draw["clear_producer_record"] is not None
        return "retained_clear"
    if kind == "unmatched_indirect":
        assert draw["no_attachment_write"]
        return "retained_no_write"
    assert kind == "direct_root", (draw["ordinal"], kind)
    assert draw["title_packet_view_call"] == 8
    caller = draw["title_packet_caller_lr"]
    if caller == 0x8243C8FC:
        assert draw["title_direct_record"]
        return "selected_character"
    if caller == 0x82415D1C:
        assert draw["title_item_node"]
        return "selected_procedural_item"
    if caller == 0x82412E1C:
        target = draw["title_second_draw_target"]
        if target == 0x824136F0:
            assert draw["title_second_draw_bound_record"] and \
                draw["title_second_draw_vegetation_owner"]
            return "selected_vegetation"
        if target == 0x8245AB88:
            assert draw["title_second_draw_bound_record"] and \
                not draw["title_second_draw_vegetation_owner"]
            return "selected_procedural_character"
        assert not target and not draw["title_second_draw_bound_record"]
        return "retained_sky"
    if caller == 0x824131F4:
        scalar = draw["title_scalar_caller_lr"]
        if scalar == 0x82415A28:
            assert draw["title_scalar_dispatch_object"] and \
                draw["title_scalar_child_context"]
            return "selected_animated"
        if scalar in CAR_SCALAR:
            assert draw["title_scalar_outer_object"]
            return "selected_car_presentation"
        assert scalar in SKID_SCALAR, (draw["ordinal"], scalar)
        return "retained_skid"
    assert caller in RETAINED_DIRECT, (draw["ordinal"], caller)
    return "retained_presentation"


def partition(path: Path) -> dict:
    raw = path.read_bytes()
    ledger = json.loads(raw)
    assert ledger["schema"] == "pinyon-shift.snr01-frame-wide-census.v1"
    assert ledger["safety"] == {"metadata_only": True,
                                "suppression_allowed": False}
    rows = ledger["draws"]
    assert len(rows) == ledger["totals"]["draws"]
    assert len({row["ordinal"] for row in rows}) == len(rows)
    totals = collections.Counter()
    by_target = collections.defaultdict(collections.Counter)
    for draw in rows:
        category = role(draw)
        totals[category] += 1
        by_target[draw["target"]][category] += 1
    assert CANDIDATE <= set(by_target)
    assert sum(totals.values()) == len(rows)
    selected = sum(count for name, count in totals.items()
                   if name.startswith("selected_"))
    retained = sum(count for name, count in totals.items()
                   if name.startswith("retained_"))
    outside = sum(count for name, count in totals.items()
                  if name.startswith("outside_"))
    assert selected + retained + outside == len(rows)
    return {"schema": "pinyon-shift.gate-a-slice-partition.v1",
            "ledger_sha256": hashlib.sha256(raw).hexdigest(),
            "backend_frame": ledger["backend_frame"],
            "draws": len(rows), "selected_draws": selected,
            "retained_draws": retained,
            "outside_draws": outside,
            "unattributed_draws": totals["outside_unattributed_direct"],
            "full_owner_census": totals["outside_unattributed_direct"] == 0,
            "roles": dict(sorted(totals.items())),
            "targets": {key: dict(sorted(value.items()))
                        for key, value in sorted(by_target.items())}}


if __name__ == "__main__":
    assert len(sys.argv) == 2, "usage: partition-snr00-gate-a-slice.py LEDGER"
    print(json.dumps(partition(Path(sys.argv[1])), sort_keys=True))
