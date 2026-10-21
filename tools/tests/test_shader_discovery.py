import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "shader_discovery", Path(__file__).parents[1] / "discover-fh1-shaders.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)

NAME = "shader_0000000000000001_0000000000000002_0000000000000003.spv"


def capture(tmp_path):
    (tmp_path / NAME).touch()
    surface = {"key": "12345678", "depth": False, "slot": 1, "width": 1280,
               "height": 720, "samples": 1, "format": 0}
    draw = {"frame": 300, "vertex": "", "pixel": NAME, "hud": True, "surfaces": [surface]}
    (tmp_path / "draws.jsonl").write_text(json.dumps(draw) + "\n" + json.dumps(draw) + "\n")


def test_lists_exact_identity_and_surfaces(tmp_path):
    capture(tmp_path)
    entries = discovery.discover(tmp_path)
    assert len(entries) == 1
    assert entries[0]["draws"] == [1, 2]
    assert entries[0]["hud_draws"] == [1, 2]
    assert len(entries[0]["surfaces"]) == 1
    assert entries[0]["translated_hash"] == "0000000000000003"


def test_stale_translation_is_distinct_from_unseen_shader(tmp_path):
    capture(tmp_path)
    shaders = tmp_path / "shaders"
    shaders.mkdir()
    names = [NAME, NAME.replace("0003.spv", "0004.spv"),
             NAME.replace("0001_", "0005_"), "shader_bad.spv"]
    for name in names:
        (shaders / name).touch()
    checks = {row["file"]: row["status"] for row in
              discovery.check_mod(discovery.discover(tmp_path), shaders)}
    assert [checks[name] for name in names] == [
        "matches capture", "stale translation", "not seen in this frame", "invalid filename"]


def test_missing_shader_and_empty_capture_fail(tmp_path):
    capture(tmp_path)
    (tmp_path / NAME).unlink()
    with pytest.raises(ValueError, match="missing or invalid"):
        discovery.discover(tmp_path)
    (tmp_path / "draws.jsonl").write_text("")
    with pytest.raises(ValueError, match="no shaders"):
        discovery.discover(tmp_path)
