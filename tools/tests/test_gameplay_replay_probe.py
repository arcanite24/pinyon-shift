import importlib.util
import json
import struct
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "replay_probe", Path(__file__).resolve().parents[1] / "inspect-fh1-gameplay-replay.py")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class Memory:
    def __init__(self):
        self.data = {}
        for at, expected in PROBE.BASE_LAYOUT.items():
            self.u32(at, expected)

    def put(self, at, data):
        self.data.update((at + i, value) for i, value in enumerate(data))

    def u32(self, at, value):
        self.put(at, struct.pack(">I", value))

    def read(self, at, size):
        try:
            return bytes(self.data[at + i] for i in range(size))
        except KeyError as error:
            raise PROBE.ProbeError("unmapped fixture address") from error


def fixture():
    memory = Memory()
    manager, sentinel, node, stream, backing = (0x10000 * n for n in range(1, 6))
    memory.u32(PROBE.MANAGER_POINTER, manager)
    memory.put(manager, bytes(600))
    memory.u32(manager, PROBE.MANAGER_VTABLE)
    memory.u32(manager + 416, sentinel)
    memory.u32(manager + 420, 1)
    memory.put(sentinel, bytes(70))
    memory.u32(sentinel + 4, node)
    memory.put(sentinel + 69, b"\1")
    memory.put(node, bytes(70))
    for offset in (0, 4, 8):
        memory.u32(node + offset, sentinel)
    for offset, value in ((12, 1), (16, stream), (20, 2), (24, 0)):
        memory.u32(node + offset, value)
    memory.put(node + 32, b"Replay")
    memory.u32(node + 48, 6)
    memory.u32(node + 52, 15)
    memory.put(stream, bytes(48))
    memory.u32(stream, PROBE.STREAM_VTABLE)
    memory.put(stream + 8, struct.pack(">f", 1.25))
    memory.u32(stream + 12, backing)
    memory.u32(backing, 0x8222C004)
    return memory, manager, sentinel, node, stream


def test_base_stream_metadata():
    memory, _, _, _, stream = fixture()
    memory.u32(stream + 24, 0x60000)
    memory.u32(stream + 28, 0x60010)
    memory.u32(stream + 32, 0x60020)
    result = PROBE.sample(PROBE.Guest(memory.read))
    assert result["state"] == "observed"
    assert result["streams"] == [{
        "id": 1, "name": "Replay", "mode": 2, "kind": 0, "parent_id": 0,
        "stream": "0x00040000", "anchor_time": 1.25,
        "backing": "0x00050000", "backing_vtable": "0x8222C004",
        "index_entries": 4, "index_flag_16": 0}]


def test_not_constructed_is_valid_observation():
    memory = Memory()
    memory.u32(PROBE.MANAGER_POINTER, 0)
    assert PROBE.sample(PROBE.Guest(memory.read)) == {"state": "not_created", "streams": []}


def test_incompatible_layout_is_rejected_before_manager_construction():
    memory = Memory()
    memory.u32(PROBE.MANAGER_POINTER, 0)
    memory.u32(PROBE.STREAM_VTABLE, 0)
    with pytest.raises(PROBE.ProbeError, match="unsupported executable layout"):
        PROBE.sample(PROBE.Guest(memory.read))


def test_heap_stream_name():
    memory, _, _, node, _ = fixture()
    memory.u32(node + 32, 0x60000)
    memory.put(0x60000, b"a longer stream name")
    memory.u32(node + 48, 20)
    memory.u32(node + 52, 31)
    assert PROBE.sample(PROBE.Guest(memory.read))["streams"][0]["name"] == "a longer stream name"


@pytest.mark.parametrize("target,offset,value,match", [
    (1, 0, 0, "vtable mismatch"),
    (1, 420, 65, "too many"),
    (2, 69, 0, "sentinel"),
    (3, 0, 0x30000, "cycle"),
    (3, 48, 200, "stream name"),
    (4, 0, 0, "implementation"),
    (4, 24, 0x60000, "index bounds"),
    (4, 8, 0x7FC00000, "non-finite"),
])
def test_rejects_invalid_or_incompatible_state(target, offset, value, match):
    memory, *_ = fixture()
    if offset == 69:
        memory.put(target * 0x10000 + offset, bytes([value]))
    else:
        memory.u32(target * 0x10000 + offset, value)
    with pytest.raises(PROBE.ProbeError, match=match):
        PROBE.sample(PROBE.Guest(memory.read))


def test_rejects_changed_tree():
    memory, manager, *_ = fixture()
    reads = 0

    def read(at, size):
        nonlocal reads
        if at == manager + 412:
            reads += 1
            if reads == 2:
                memory.u32(manager + 420, 0)
        return memory.read(at, size)

    with pytest.raises(PROBE.ProbeError, match="changed"):
        PROBE.sample(PROBE.Guest(read))


@pytest.mark.parametrize("at,size", [(0, 4), (0xFFFFFFFE, 4), (0x10000, 1 << 21)])
def test_memory_reads_are_bounded(at, size):
    def never_read(*args):
        pytest.fail("invalid range reached the OS reader")
    with pytest.raises(PROBE.ProbeError, match="range"):
        PROBE.Guest(never_read).bytes(at, size)


def test_requires_one_arena_in_log():
    line = "Guest memory arena mapped: virtual base 0x0000000100000000, physical base 0x200000000"
    assert PROBE.virtual_base(line) == 0x100000000
    for log in ("", line + "\n" + line):
        with pytest.raises(PROBE.ProbeError, match="exactly one"):
            PROBE.virtual_base(log)


@pytest.mark.parametrize("valid", [True, False])
def test_cli_reports_samples_and_closes_reader(tmp_path, monkeypatch, valid):
    memory, manager, *_ = fixture()
    if not valid:
        memory.u32(manager, 0)
    closed = []

    class Reader:
        def __init__(self, pid, base):
            assert pid == 42 and base == 0x100000000
        read = staticmethod(memory.read)
        def close(self):
            closed.append(True)

    output = tmp_path / "probe.jsonl"
    monkeypatch.setattr(PROBE, "WindowsReader", Reader)
    monkeypatch.setattr(PROBE.sys, "argv", ["probe", "--pid", "42", "--guest-base", "0x100000000",
                                         "--output", str(output)])
    assert PROBE.main() == (0 if valid else 1)
    row = json.loads(output.read_text())
    assert row["schema"] == PROBE.SCHEMA and row["pid"] == 42
    assert row["state"] == ("observed" if valid else "unavailable")
    assert closed == [True]


def test_cli_preserves_existing_output_and_closes_reader(tmp_path, monkeypatch):
    closed = []

    class Reader:
        def __init__(self, pid, base):
            pass
        read = staticmethod(lambda at, size: bytes(size))
        def close(self):
            closed.append(True)

    output = tmp_path / "probe.jsonl"
    output.write_text("keep this evidence")
    monkeypatch.setattr(PROBE, "WindowsReader", Reader)
    monkeypatch.setattr(PROBE.sys, "argv", ["probe", "--pid", "42", "--guest-base", "0x100000000",
                                         "--output", str(output)])
    assert PROBE.main() == 1
    assert output.read_text() == "keep this evidence"
    assert closed == [True]


def test_cli_rejects_invalid_base_before_opening_process(monkeypatch):
    def never_open(*args):
        pytest.fail("invalid base reached the OS reader")
    monkeypatch.setattr(PROBE, "WindowsReader", never_open)
    monkeypatch.setattr(PROBE.sys, "argv", ["probe", "--pid", "42", "--guest-base", "0"])
    assert PROBE.main() == 1
