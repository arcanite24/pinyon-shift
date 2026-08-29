import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "export-native-renderer-renderdoc.py"


class FakeResourceId:
    @staticmethod
    def Null():
        return "null"


fake_renderdoc = types.SimpleNamespace(
    ResourceId=FakeResourceId,
    ActionFlags=types.SimpleNamespace(Drawcall=1),
)
sys.modules.setdefault("renderdoc", fake_renderdoc)
SPEC = importlib.util.spec_from_file_location("native_renderdoc_export", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Action:
    def __init__(self, name, event_id):
        self.customName = name
        self.eventId = event_id
        self.flags = 0
        self.children = []


def marker_chain():
    return [
        Action(MODULE.PASS_NATIVE_ANCHOR_MARKER, 10),
        Action(MODULE.PASS_XENOS_ANCHOR_MARKER, 20),
        Action(MODULE.PASS_NATIVE_FOLLOWER_MARKER, 30),
        Action(MODULE.PASS_XENOS_FOLLOWER_MARKER, 40),
    ]


def span(resource_id):
    target = {"resource_id": resource_id, "width": 640, "height": 8192}
    return {"before": {"color": target}, "after": {"color": target}}


class NativeRendererRenderDocExportTests(unittest.TestCase):
    def test_complete_pass_requires_ordered_distinct_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.rdc"
            capture.write_bytes(b"capture")

            def export_span(_, first, last, __, basename):
                self.assertLess(first.eventId, last.eventId)
                return span("native" if basename == "isolated-native" else "xenos")

            with mock.patch.object(MODULE, "_export_pass_span", export_span):
                result = MODULE._export_complete_pass(
                    object(), marker_chain(), str(capture), temporary
                )

        self.assertEqual(result["schema"], MODULE.COMPLETE_PASS_SCHEMA)
        self.assertEqual(result["marker_order"], [10, 20, 30, 40])
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertFalse(result["safety"]["draw_suppression_implemented"])

    def test_complete_pass_rejects_missing_follower(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.rdc"
            capture.write_bytes(b"capture")
            with self.assertRaisesRegex(RuntimeError, "marker chain"):
                MODULE._export_complete_pass(
                    object(), marker_chain()[:-1], str(capture), temporary
                )

    def test_complete_pass_rejects_native_xenos_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / "capture.rdc"
            capture.write_bytes(b"capture")
            with mock.patch.object(
                MODULE, "_export_pass_span", return_value=span("shared")
            ):
                with self.assertRaisesRegex(RuntimeError, "outputs alias"):
                    MODULE._export_complete_pass(
                        object(), marker_chain(), str(capture), temporary
                    )


if __name__ == "__main__":
    unittest.main()
