import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-assembly-shadow.py"
SPEC = importlib.util.spec_from_file_location("visibility_assembly_shadow", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityAssemblyShadowReportTests(unittest.TestCase):
    def static(self):
        return {
            "procedural_model_receiver_lifecycle": {
                "visibility_policy_assembly_shadow": {
                    "record_entry_hook_address": "82E20094",
                    "spatial_input_hook_address": "82E2034C",
                    "spatial_result_hook_address": "82E20350",
                    "category_input_hook_address": "82E20364",
                    "category_result_hook_address": "82E20368",
                    "title_result_hook_address": "82E206F8",
                    "record_exit_hook_address": "82E2084C",
                    "model": "independent_spatial_then_category_selection",
                    "selection_rule": (
                        "any_nonzero_predicted_category_result_selects"
                    ),
                    "bounded_guest_payload_bytes_per_candidate": 148,
                    "scope": "active_title_record_only",
                    "title_outcome_comparison_required": True,
                    "guest_payload_read": "bounded_spatial_and_category_inputs",
                    "guest_state_changed": False,
                    "control_flow_changed": False,
                    "native_policy_execution": "shadow_only",
                    "native_culling_enabled": False,
                    "native_lod_enabled": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                }
            }
        }

    def config(self):
        return {
            "event": MODULE.CONFIG,
            "session": "test",
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "visibility_function": "82E1FD00",
            "record_entry_hook": "82E20094",
            "spatial_input_hook": "82E2034C",
            "spatial_result_hook": "82E20350",
            "category_input_hook": "82E20364",
            "category_result_hook": "82E20368",
            "title_result_hook": "82E206F8",
            "record_completion_hook": "82E2084C",
            "model": "independent_spatial_then_category_selection",
            "selection_rule": "any_nonzero_predicted_category_result_selects",
            "bounded_guest_payload_bytes_per_candidate": "148",
            "scope": "active_title_record_only",
            "classification": "independent_visibility_policy_assembly_shadow",
            "guest_payload_read": "bounded_spatial_and_category_inputs",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "shadow_only",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }

    def row(self, outcome, records, modelled, selected, results):
        rejected = modelled - selected
        spatial_inputs = sum(results) + (1 if outcome == "early_rejected" else 2)
        base = {
            "session": "test",
            "status": "complete",
            "category": "9",
            "outcome": outcome,
        }
        return [
            {
                **base,
                "event": MODULE.ORACLE_CATEGORY,
                "records": str(records),
                "category_result_0": str(results[0]),
                "category_result_1": str(results[1]),
                "category_result_2": str(results[2]),
            },
            {
                **base,
                "event": MODULE.SPATIAL_CATEGORY,
                "input_observations": str(spatial_inputs),
            },
            {
                **base,
                "event": MODULE.CATEGORY_SHADOW_CATEGORY,
                "input_observations": str(sum(results)),
            },
            {
                **base,
                "event": MODULE.CATEGORY,
                "records": str(records),
                "modelled_records": str(modelled),
                "predicted_selected": str(selected),
                "predicted_rejected": str(rejected),
                "title_matches": str(modelled),
                "false_positive": "0",
                "false_negative": "0",
                "spatial_input_observations": str(spatial_inputs),
                "spatial_predicted_passes": str(sum(results)),
                "category_input_observations": str(sum(results)),
                "category_result_0": str(results[0]),
                "category_result_1": str(results[1]),
                "category_result_2": str(results[2]),
                "invalid_inputs": "0",
                "native_policy_execution": "shadow_only",
                "guest_payload_read": "bounded_spatial_and_category_inputs",
                "guest_state_changed": "false",
                "xenos_authority": "true",
                "suppression_allowed": "false",
            },
        ]

    def events(self):
        rows = [
            ("early_rejected", 4, 0, 0, (0, 0, 0)),
            ("rejected", 2, 2, 0, (4, 0, 0)),
            ("selected", 1, 1, 1, (0, 1, 2)),
        ]
        events = [self.config()]
        for row in rows:
            events.extend(self.row(*row))
        events.append(
            {
                "event": MODULE.SUMMARY,
                "session": "test",
                "status": "complete",
                "records": "7",
                "modelled_records": "3",
                "unmodelled_records": "4",
                "predicted_selected": "1",
                "predicted_rejected": "2",
                "title_matches": "3",
                "false_positive": "0",
                "false_negative": "0",
                "spatial_input_observations": "12",
                "spatial_predicted_passes": "7",
                "category_input_observations": "7",
                "category_result_0": "4",
                "category_result_1": "1",
                "category_result_2": "2",
                "invalid_inputs": "0",
                "accounting_complete": "true",
                "model": "independent_spatial_then_category_selection",
                "scope": "active_title_record_only",
                "classification": "independent_visibility_policy_assembly_shadow",
                "guest_payload_read": "bounded_spatial_and_category_inputs",
                "guest_state_changed": "false",
                "control_flow_changed": "false",
                "native_policy_execution": "shadow_only",
                "native_culling": "false",
                "native_lod": "false",
                "xenos_authority": "true",
                "suppression_allowed": "false",
            }
        )
        return events

    def assembly_event(self, events, outcome="selected"):
        return next(
            event
            for event in events
            if event.get("event") == MODULE.CATEGORY
            and event.get("outcome") == outcome
        )

    def test_build_qualifies_independent_policy_assembly(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(3, document["totals"]["title_matches"])
        self.assertTrue(
            document["qualification"][
                "independent_visibility_policy_assembly_shadow_proved"
            ]
        )
        self.assertFalse(document["safety"]["guest_state_changed"])
        self.assertTrue(document["safety"]["xenos_authority"])

    def test_build_rejects_false_positive(self):
        events = copy.deepcopy(self.events())
        item = self.assembly_event(events)
        item["title_matches"] = "0"
        item["false_positive"] = "1"
        with self.assertRaisesRegex(ValueError, "comparison failed"):
            MODULE.build(events, self.static())

    def test_build_rejects_invalid_input(self):
        events = copy.deepcopy(self.events())
        self.assembly_event(events)["invalid_inputs"] = "1"
        with self.assertRaisesRegex(ValueError, "comparison failed"):
            MODULE.build(events, self.static())

    def test_build_rejects_oracle_result_drift(self):
        events = copy.deepcopy(self.events())
        oracle = next(
            event
            for event in events
            if event.get("event") == MODULE.ORACLE_CATEGORY
            and event.get("outcome") == "selected"
        )
        oracle["category_result_2"] = "1"
        with self.assertRaisesRegex(ValueError, "oracle reconciliation failed"):
            MODULE.build(events, self.static())

    def test_build_rejects_static_contract_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_policy_assembly_shadow"
        ]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)

    def test_build_rejects_runtime_safety_drift(self):
        events = copy.deepcopy(self.events())
        events[0]["xenos_authority"] = "false"
        with self.assertRaisesRegex(ValueError, "configuration drifted"):
            MODULE.build(events, self.static())


if __name__ == "__main__":
    unittest.main()
