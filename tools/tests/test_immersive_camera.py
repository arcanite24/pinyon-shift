import runpy
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
CAMERA = runpy.run_path(str(ROOT / "tools/build-immersive-camera.py"))


def test_base_and_v4_layers_match_their_own_counts(tmp_path):
    for name, stock, committed in (("base", CAMERA["STOCK"], CAMERA["DEFAULT"]),
                                    ("v4", CAMERA["STOCK_V4"], CAMERA["DEFAULT_V4"])):
        output = tmp_path / name / "camera.xml"
        CAMERA["main"](output, stock)
        assert output.read_bytes() == committed.read_bytes()
        for camera in ET.parse(output).getroot():
            assert int(camera.get("NumLayers")) == stock[camera.tag] + len(camera)
            assert all(layer.get("pinyon-add") == "true" for layer in camera)
            for layer in camera:
                value = float(layer.get("SpringK") if layer.get("Sprung") == "1" else layer.get("NoiseSeed"))
                group = round((value % 1 - CAMERA["TAG"]) / CAMERA["TAG_STEP"])
                assert 1 <= group <= 4


def test_camera_editor_route_parses():
    runner = runpy.run_path(str(ROOT / "tools/run-fh1-render-test.py"))
    for name in ("fh1-camera-editor", "fh1-camera-editor-ui"):
        runner["parse_scenario"](ROOT / f"config/render-tests/{name}.fh1test")
