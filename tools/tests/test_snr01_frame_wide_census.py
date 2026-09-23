"""Check frame-wide draw accounting across two title source frames."""

import runpy
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "summarize-snr01-frame-wide-census.py")
)
SUMMARIZE = SCRIPT["summarize"]
READ_RECORDS = SCRIPT["read_records"]
VERIFY_CAR_TEXTURE = SCRIPT["verify_car_texture_resolution"]


class FrameWideCensusTest(unittest.TestCase):
    def test_car_texture_resolution_joins_selected_resource_and_fetch(self):
        records = {
            "car_texture": [{"frame": 10, "next_direct": 5, "slot": 0,
                             "resource": 100, "resolved": 200,
                             "descriptor_words": [0, 0x1006,
                                                  (63 << 13) | 63, 0, 0, 0]}],
            "draw": [{"ordinal": i, "texture_fetch_count": 1} for i in (1, 2)],
            "texture_fetch": [
                {"draw": i, "packet_physical": 300, "fetch_constant": 0,
                 "base_address": 0x1000, "mip_address": 0, "format": 6,
                 "width": 64, "height": 64} for i in (1, 2)],
        }
        result = {"draws": [
            {"target": "14020500/color", "title_scalar_caller_lr": 0x82444018,
             "title_packet_ordinal": 5, "title_scalar_outer_field16": 0,
             "title_scalar_outer_field12": 100, "ordinal": i,
             "packet_physical": 300} for i in (1, 2)]}
        VERIFY_CAR_TEXTURE(records, result, 10, True)
        records["texture_fetch"][1]["base_address"] = 401
        with self.assertRaises(AssertionError):
            VERIFY_CAR_TEXTURE(records, result, 10, True)
        records["texture_fetch"][1]["base_address"] = 0x1000
        records["car_texture"][0]["descriptor_words"][1] = 0x1007
        with self.assertRaises(AssertionError):
            VERIFY_CAR_TEXTURE(records, result, 10, True)
        records["car_texture"][0]["descriptor_words"][1] = 0x1006
        records["car_texture"][0]["resource"] = 101
        with self.assertRaises(AssertionError):
            VERIFY_CAR_TEXTURE(records, result, 10, True)

    def test_direct_packet_inherits_only_its_thread_view_scope(self):
        events = (
            ("view begin", {"frame": 10, "call": 8, "view": 123}),
            ("direct packet", {"frame": 10, "header_physical": 4}),
            ("second draw call", {"frame": 10, "first_direct": 1,
                                  "last_direct": 1}),
            ("view end", {"frame": 10, "call": 8, "view": 123}),
            ("direct packet", {"frame": 10, "header_physical": 8}),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.log"
            path.write_text("".join(
                f"[t7] FH1 SNR01 {kind} {json.dumps(row)}\n"
                for kind, row in events), encoding="utf-8")
            records = READ_RECORDS(path, {10, 11}, 11)
            rows = records["direct"]
        self.assertEqual([row["title_view_call"] for row in rows], [8, 0])
        self.assertEqual(records["second_draw"][0]["title_thread"], 7)

    def test_scene_owner_direct_root_and_unmatched_child(self):
        records = {key: [] for key in SCRIPT["PREFIXES"]}
        for frame in (10, 11):
            for call in range(1, 9):
                row = {"frame": frame, "call": call, "view": frame * 100 + call}
                records["view_begin"].append(row)
                records["view_end"].append(row)
        records["primary"] = [
            {"frame": 10, "header_physical": 100, "gpu_target": 1000},
            {"frame": 11, "header_physical": 200, "gpu_target": 2000},
        ]
        records["scene"] = [
            {"frame": 10, "header_physical": 300, "target_physical": 3000,
             "view_call": 8, "view": 1008, "flush_owner": 400,
             "flush_owner_first_word": 500, "flush_caller_lr": 600},
        ]
        records["execution"] = [
            {"execution": 1, "parent": 0, "dispatch_packet_physical": 100,
             "command_buffer": 1000},
            {"execution": 2, "parent": 1, "dispatch_packet_physical": 300,
             "command_buffer": 3000},
            {"execution": 3, "parent": 0, "dispatch_packet_physical": 200,
             "command_buffer": 2000},
            {"execution": 4, "parent": 3, "dispatch_packet_physical": 400,
             "command_buffer": 4000},
        ]
        records["draw"] = [
            {"ordinal": ordinal, "indirect_execution": execution,
             "surface_info": 1, "color_info": [2], "depth_info": 3,
             "render_target_bits": 3, "packet_physical": ordinal * 4,
             "depth_control": 0, "color_mask": 0}
            for ordinal, execution in enumerate((2, 1, 4, 3), 1)
        ]
        records["draw"][0]["color_mask"] = 15
        records["draw"][1]["depth_control"] = 2
        records["draw"][1]["packet_bytes"] = 4
        records["clear"] = [
            {"frame": 10, "record": 7, "flags": 63,
             "command_cursor_before": 0xA0000006,
             "command_cursor_after": 0xA000000C,
             "refills": 0, "nested": False},
        ]
        result = SUMMARIZE(records, [10, 11], 11)
        self.assertEqual(result["totals"]["draws"], 4)
        self.assertEqual(result["totals"]["classifications"],
                         {"view_owner": 1, "title_clear": 1, "direct_root": 1,
                          "unmatched_indirect": 1})
        self.assertEqual(result["totals"]["draws_by_scene_source_frame"], {10: 1})
        self.assertEqual(result["targets"]["00000001/00000002/00000003/00000003"]
                         ["no_attachment_write_draws"], 2)
        self.assertEqual(len(result["draws"]), 4)
        self.assertEqual(result["draws"][1]["clear_producer_record"], 7)
        records["clear"][0]["refills"] = 1
        self.assertEqual(SUMMARIZE(records, [10, 11], 11)["draws"][1]
                         ["classification"], "direct_root")
        records["clear"][0].update(refills=0, _log_order=10)
        records["primary"][0].update(frame=11, _log_order=20)
        draw = SUMMARIZE(records, [10, 11], 11)["draws"][1]
        self.assertEqual((draw["classification"], draw["clear_producer_record"],
                          draw["clear_producer_source_frame"]),
                         ("title_clear", 7, 10))
        records["clear"][0]["_log_order"] = 30
        self.assertEqual(SUMMARIZE(records, [10, 11], 11)["draws"][1]
                         ["classification"], "direct_root")
        records["clear"][0].update(refills=1, _log_order=10,
                                   command_cursor_before=0xA0001000)
        records["primary"][0]["gpu_target"] = 4
        records["execution"][0]["command_buffer"] = 4
        self.assertEqual(SUMMARIZE(records, [10, 11], 11)["draws"][1]
                         ["clear_producer_record"], 7)
        records["clear"][0]["command_cursor_after"] = 0xA0002000
        self.assertEqual(SUMMARIZE(records, [10, 11], 11)["draws"][1]
                         ["classification"], "direct_root")


if __name__ == "__main__":
    unittest.main()
