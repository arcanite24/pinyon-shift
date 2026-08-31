import importlib.util
import pathlib
import tempfile
import unittest


SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "build-native-renderer-static-world-instance-catalog.py"
)
SPEC = importlib.util.spec_from_file_location("static_world_instance_catalog", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


COLLISION = """<?xml version="1.0"?>
<CollObjs>
  <Obj0 PhysicsType="CO_Prop.rmb" GraphicsName="#17">
    <Pos x="1.25" y="2.5" z="-3.75"/>
    <Orientation>
      <XAxis x="1" y="0" z="0"/>
      <YAxis x="0" y="1" z="0"/>
      <ZAxis x="0" y="0" z="1"/>
    </Orientation>
  </Obj0>
</CollObjs>
"""

GAMEPLAY = """<?xml version="1.0"?>
<GameObjs>
  <Obj0 GameplayID="GAMEPLAY_MARKER">
    <Pos x="10" y="20" z="30"/>
    <Orientation>
      <XAxis x="0" y="0" z="1"/>
      <YAxis x="0" y="1" z="0"/>
      <ZAxis x="-1" y="0" z="0"/>
    </Orientation>
  </Obj0>
</GameObjs>
"""


class StaticWorldInstanceCatalogTests(unittest.TestCase):
    def build(self, collision=COLLISION, gameplay=GAMEPLAY):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            collision_path = root / "CollObjs.xml"
            gameplay_path = root / "GameObjs.xml"
            collision_path.write_text(collision, encoding="utf-8")
            gameplay_path.write_text(gameplay, encoding="utf-8")
            return MODULE.build(collision_path, gameplay_path)

    def test_catalogs_hashed_spatial_metadata(self):
        document = self.build()
        self.assertEqual(MODULE.SCHEMA, document["schema"])
        self.assertEqual(2, document["instance_count"])
        self.assertEqual(
            ["collision_prop", "gameplay_object"],
            [item["category"] for item in document["instances"]],
        )
        self.assertEqual(
            [1.25, 2.5, -3.75], document["instances"][0]["position"]
        )
        self.assertEqual(16, len(document["instances"][0]["identity_hash"]))
        self.assertFalse(
            document["qualification"]["runtime_transform_join_proved"]
        )
        self.assertNotIn("CO_Prop", str(document))
        self.assertNotIn("GAMEPLAY_MARKER", str(document))

    def test_rejects_non_finite_spatial_data(self):
        with self.assertRaisesRegex(ValueError, "non-finite position"):
            self.build(COLLISION.replace('x="1.25"', 'x="nan"'))

    def test_rejects_wrong_root(self):
        with self.assertRaisesRegex(ValueError, "expected CollObjs root"):
            self.build(COLLISION.replace("CollObjs", "WrongRoot"))


if __name__ == "__main__":
    unittest.main()
