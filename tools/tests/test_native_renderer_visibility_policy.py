import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-policy.py"
SPEC = importlib.util.spec_from_file_location("visibility_policy", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def static_contract():
    return {
        "procedural_model_receiver_lifecycle": {
            "visibility_policy_inputs": {
                "spatial_prefilter_address": "82E1FEF0",
                "receiver_spatial_context_pointer_offset": 4,
                "receiver_spatial_vector_offsets": [16, 32],
                "category_spatial_argument_register": "r4",
                "category_spatial_stride": 192,
                "category_spatial_scalar_offsets": [160, 164, 168],
                "category_query_argument_register": "r5",
                "category_query_stride": 32,
                "spatial_helper_address": "8243F9A0",
                "category_helper_address": "82441048",
                "descriptor_distance_scalar_offset": 60,
                "runtime_distance_scalar_offset": 44,
                "squared_distance_register": "f26",
                "threshold_register": "f0",
                "runtime_threshold_hook_address": "82E20134",
                "descriptor_threshold_hook_address": "82E201B0",
                "passive_input_outcome_correlation_required": True,
                "spatial_helper_contract": {
                    "distance_helper_address": "8243FD70",
                    "query_vector_offset": 0,
                    "query_scalar_offsets": [16, 20, 24],
                    "segment_endpoint_registers": ["v1", "v2"],
                    "squared_delta_operation": "vmsum3fp128",
                    "distance_test_structure_proved": True,
                    "world_space_semantics_proved": False,
                },
                "category_helper_contract": {
                    "vector_block_offsets": [0, 16, 32, 48, 64, 80],
                    "vector_block_count": 6,
                    "input_registers": ["v1", "v2"],
                    "return_domain": [0, 1, 2],
                    "six_vector_classifier_structure_proved": True,
                    "frustum_semantics_proved": False,
                },
                "structural_derivation_proved": True,
                "camera_semantics_proved": False,
                "frustum_plane_layout_proved": False,
                "bounds_shape_semantics_proved": False,
                "native_policy_execution_enabled": False,
                "guest_state_changed": False,
                "xenos_authority": True,
                "suppression_allowed": False,
            }
        }
    }


def events():
    common = {"session": "policy-session"}
    safe = {
        "native_policy_execution": "false",
        "guest_state_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    result = [
        {
            **common,
            "event": MODULE.CONFIG,
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "visibility_function": "82E1FD00",
            "record_entry_hook": "82E20094",
            "runtime_threshold_hook": "82E20134",
            "descriptor_threshold_hook": "82E201B0",
            "spatial_distance_source": "f26",
            "threshold_source": "f0",
            "runtime_distance_scalar_offset": "44",
            "descriptor_distance_scalar_offset": "60",
            "spatial_exponent_capacity": "256",
            "outcomes": "early_rejected,rejected,selected",
            "scope": "active_title_record_only",
            "classification": "title_spatial_policy_input_outcome_correlation",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "false",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.VISIBILITY_CATEGORY,
            "status": "complete",
            "category": "9",
            "entries": "5",
            "completions": "5",
            "selected": "2",
            "rejected": "1",
            "early_rejected": "2",
            "lod_writes": "2",
        },
    ]
    counts = {
        "early_rejected": (2, 1, 1, 2, 1),
        "rejected": (1, 1, 0, 1, 0),
        "selected": (2, 2, 1, 2, 0),
    }
    for outcome, (records, runtime, less, descriptor, exceeded) in counts.items():
        result.append(
            {
                **common,
                **safe,
                "event": MODULE.CATEGORY,
                "status": "complete",
                "category": "9",
                "outcome": outcome,
                "records": str(records),
                "spatial_samples": str(records),
                "runtime_threshold_observations": str(runtime),
                "runtime_distance_less": str(less),
                "descriptor_threshold_observations": str(descriptor),
                "descriptor_distance_exceeded": str(exceeded),
            }
        )
        result.append(
            {
                **common,
                **safe,
                "event": MODULE.EXPONENT,
                "status": "complete",
                "outcome": outcome,
                "float_exponent": "127",
                "records": str(records),
                "source": "title_shared_spatial_distance_squared_f26",
            }
        )
    result.append(
        {
            **common,
            "event": MODULE.SUMMARY,
            "status": "complete",
            "records": "5",
            "spatial_samples": "5",
            "runtime_threshold_observations": "4",
            "runtime_distance_less": "2",
            "descriptor_threshold_observations": "5",
            "descriptor_distance_exceeded": "1",
            "spatial_histogram_records": "5",
            "invalid_spatial_values": "0",
            "invalid_threshold_values": "0",
            "hook_faults": "0",
            "runtime_threshold_without_record": "0",
            "duplicate_runtime_threshold": "0",
            "descriptor_threshold_without_record": "0",
            "duplicate_descriptor_threshold": "0",
            "accounting_complete": "true",
            "scope": "active_title_record_only",
            "unscoped_continuations_excluded": "true",
            "classification": "title_spatial_policy_input_outcome_correlation",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "false",
            "native_culling": "false",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
    )
    return result


class VisibilityPolicyTests(unittest.TestCase):
    def test_accepts_complete_passive_correlation(self):
        document = MODULE.build(events(), static_contract())
        self.assertEqual(MODULE.SCHEMA, document["schema"])
        self.assertEqual(5, document["totals"]["records"])
        self.assertEqual(2, document["totals"]["runtime_distance_less"])
        self.assertTrue(
            document["qualification"]["title_input_outcome_correlation_proved"]
        )
        self.assertFalse(
            document["qualification"]["native_policy_execution_enabled"]
        )

    def test_rejects_hook_fault(self):
        broken = events()
        broken[-1]["hook_faults"] = "1"
        broken[-1]["duplicate_runtime_threshold"] = "1"
        with self.assertRaisesRegex(ValueError, "aggregate accounting"):
            MODULE.build(broken, static_contract())

    def test_rejects_category_drift(self):
        broken = events()
        broken[1]["selected"] = "3"
        with self.assertRaisesRegex(ValueError, "category accounting"):
            MODULE.build(broken, static_contract())

    def test_rejects_static_native_execution(self):
        broken = static_contract()
        broken["procedural_model_receiver_lifecycle"][
            "visibility_policy_inputs"
        ]["native_policy_execution_enabled"] = True
        with self.assertRaisesRegex(ValueError, "static visibility-policy"):
            MODULE.build(events(), broken)


if __name__ == "__main__":
    unittest.main()
