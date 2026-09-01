import importlib.util
import pathlib
import struct
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "summarize-native-renderer-direct-indexed-producers.py"
SPEC = importlib.util.spec_from_file_location("direct_indexed_runtime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SESSION = "direct-indexed-test"


def safety():
    return {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def float_word(value):
    return f"{int.from_bytes(struct.pack('>f', value), 'big'):08X}"


def events():
    result = [
        {"event": "process.start", "session": SESSION},
        {
            "event": MODULE.CONFIG,
            "session": SESSION,
            "status": "armed",
            "direct_indexed_draw_emitter": "82416380",
            "direct_indexed_draw_producer_count": "13",
            "direct_indexed_draw_producer_hook": "82416380:r26,r31,lr",
            "direct_indexed_draw_producer_census": "armed",
            "unified_track_mesh_draw_return": "82C5B038",
            "unified_track_mesh_draw_producer": "82C5ADC0",
            "unified_track_mesh_vtable": "8200143C",
            "unified_track_mesh_transform": "live_r31_16_be_u32_at_exact_draw_entry",
            "unified_track_mesh_transform_capacity": "4096",
        },
    ]
    for index, address in enumerate(MODULE.EXPECTED_RETURNS):
        observations = 16 if address == "82C5B038" else (84 if index == 0 else 0)
        result.append(
            {
                "event": MODULE.PRODUCER,
                "session": SESSION,
                "emitter": "82416380",
                "return_address": address,
                "producer_function": "82C5ADC0" if address == "82C5B038" else "82400000",
                "classification": "unified_track_presentation_mesh" if address == "82C5B038" else "fixture",
                "observations": str(observations),
                **safety(),
            }
        )
    identity = [
        float_word(1.0), float_word(0.0), float_word(0.0), float_word(0.0),
        float_word(0.0), float_word(1.0), float_word(0.0), float_word(0.0),
        float_word(0.0), float_word(0.0), float_word(1.0), float_word(0.0),
        float_word(0.0), float_word(0.0), float_word(0.0), float_word(1.0),
    ]
    for index in range(8):
        words = list(identity)
        words[12] = float_word(float(index + 1))
        result.append(
            {
                "event": MODULE.TRANSFORM,
                "session": SESSION,
                "emitter": "82416380",
                "return_address": "82C5B038",
                "producer_function": "82C5ADC0",
                "mesh_vtable": "8200143C",
                "mesh_address": f"A000{index:04X}",
                "transform_hash": f"{index + 1:016X}",
                "transform_words": ",".join(words),
                "observations": "2",
                "first_frame": str(index + 1),
                "last_frame": str(index + 2),
                "classification": "exact_unified_track_mesh_draw_transform",
                **safety(),
            }
        )
    result.extend(
        [
            {
                "event": MODULE.SUMMARY,
                "session": SESSION,
                "status": "complete",
                "observations": "100",
                "classified_observations": "100",
                "unknown_callers": "0",
                "producer_count": "13",
                "unified_track_mesh_observations": "16",
                "unified_track_mesh_exact": "16",
                "unified_track_mesh_read_faults": "0",
                "unified_track_mesh_vtable_mismatches": "0",
                "unified_track_mesh_nonfinite_transforms": "0",
                "unified_track_mesh_transform_entries": "8",
                "unified_track_mesh_transform_collisions": "0",
                "unified_track_mesh_transform_overflow": "0",
                "accounting_complete": "true",
                **safety(),
            },
            {"event": "process.shutdown", "session": SESSION},
        ]
    )
    return result


class DirectIndexedRuntimeTests(unittest.TestCase):
    def test_qualifies_exact_track_mesh_activity(self):
        report = MODULE.build(events())
        self.assertEqual("complete", report["status"])
        self.assertTrue(
            report["qualification"]["unified_track_mesh_transform_boundary_proved"]
        )
        self.assertFalse(
            report["qualification"]["building_or_prop_instance_identity_proved"]
        )

    def test_rejects_unknown_caller(self):
        observed = events()
        summary = next(event for event in observed if event["event"] == MODULE.SUMMARY)
        summary["unknown_callers"] = "1"
        summary["observations"] = "101"
        report = MODULE.build(observed)
        self.assertEqual("incomplete", report["status"])
        self.assertTrue(any("unknown" in failure for failure in report["failures"]))

    def test_rejects_too_few_transforms(self):
        observed = [event for event in events() if not (
            event.get("event") == MODULE.TRANSFORM and event.get("mesh_address") == "A0000007"
        )]
        summary = next(event for event in observed if event["event"] == MODULE.SUMMARY)
        summary["unified_track_mesh_transform_entries"] = "7"
        summary["unified_track_mesh_exact"] = "14"
        summary["unified_track_mesh_observations"] = "14"
        producer = next(event for event in observed if event.get("return_address") == "82C5B038" and event.get("event") == MODULE.PRODUCER)
        producer["observations"] = "14"
        summary["observations"] = "98"
        summary["classified_observations"] = "98"
        report = MODULE.build(observed)
        self.assertEqual("incomplete", report["status"])
        self.assertIn("too few distinct unified track mesh transforms", report["failures"])


if __name__ == "__main__":
    unittest.main()
