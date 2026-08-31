import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = (
    ROOT
    / "tools"
    / "discover-native-renderer-static-world-presentation-types.py"
)
SPEC = importlib.util.spec_from_file_location("static_world_types", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def locators():
    rows = []
    for locator, expected in MODULE.EXPECTED_SURFACES.items():
        name, object_offset, _, _, _ = expected
        type_descriptor = (
            MODULE.MODEL_PRESENTATION_TYPE
            if name == MODULE.MODEL_PRESENTATION_NAME
            else 0x832B9628
        )
        rows.append(
            {
                "locator": locator,
                "object_offset": object_offset,
                "constructor_displacement": 0,
                "type_descriptor": type_descriptor,
                "decorated_name": name,
                "hierarchy": 0x82364000 + len(rows) * 0x40,
                "hierarchy_attributes": 1,
                "bases": [
                    {
                        "type_descriptor": type_descriptor,
                        "decorated_name": name,
                    },
                    {
                        "type_descriptor": MODULE.MODEL_PRESENTATION_TYPE,
                        "decorated_name": MODULE.MODEL_PRESENTATION_NAME,
                    },
                ],
            }
        )
    return rows


def vtable_for(locator):
    _, _, vtable, slot_count, inherited = MODULE.EXPECTED_SURFACES[locator]
    return [
        {
            "vtable": vtable,
            "slot_count": slot_count,
            "slot_zero_target": 0x82DEA508,
            "slot_12_target": (
                MODULE.MODEL_PRESENTATION_DRAW if inherited else None
            ),
            "inherits_model_presentation_draw": inherited,
        }
    ]


class StaticWorldPresentationTypeTests(unittest.TestCase):
    def test_locks_complete_generic_presentation_type_census(self):
        rows = locators()
        with mock.patch.object(
            MODULE, "image_string", return_value=MODULE.MODEL_PRESENTATION_NAME
        ), mock.patch.object(MODULE, "find_locators", return_value=rows), mock.patch.object(
            MODULE,
            "find_vtables",
            side_effect=lambda _image, _functions, locator: vtable_for(locator),
        ):
            document = MODULE.build({0x82DEA508}, b"")
        self.assertEqual("complete", document["status"])
        self.assertEqual(4, document["summary"]["locator_count"])
        self.assertEqual(2, document["summary"]["unique_type_count"])
        self.assertEqual(
            2, document["summary"]["inherited_draw_surface_count"]
        )
        self.assertFalse(
            document["summary"]["concrete_building_or_prop_identity_proved"]
        )

    def test_rejects_new_or_missing_presentation_surface(self):
        rows = locators()[:-1]
        with mock.patch.object(
            MODULE, "image_string", return_value=MODULE.MODEL_PRESENTATION_NAME
        ), mock.patch.object(MODULE, "find_locators", return_value=rows), mock.patch.object(
            MODULE,
            "find_vtables",
            side_effect=lambda _image, _functions, locator: vtable_for(locator),
        ):
            with self.assertRaisesRegex(ValueError, "census drifted"):
                MODULE.build({0x82DEA508}, b"")

    def test_rejects_draw_target_drift(self):
        rows = locators()

        def drifted(_image, _functions, locator):
            result = copy.deepcopy(vtable_for(locator))
            if locator == 0x823633E8:
                result[0]["inherits_model_presentation_draw"] = False
                result[0]["slot_12_target"] = 0x823F8DBC
            return result

        with mock.patch.object(
            MODULE, "image_string", return_value=MODULE.MODEL_PRESENTATION_NAME
        ), mock.patch.object(MODULE, "find_locators", return_value=rows), mock.patch.object(
            MODULE, "find_vtables", side_effect=drifted
        ):
            with self.assertRaisesRegex(ValueError, "census drifted"):
                MODULE.build({0x82DEA508}, b"")


if __name__ == "__main__":
    unittest.main()
