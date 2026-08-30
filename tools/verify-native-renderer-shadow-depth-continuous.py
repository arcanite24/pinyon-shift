"""Verify one bounded multi-epoch shadow-depth qualification."""

import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def load_events(path):
    events = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSONL at line {line_number}: {error}"
                    ) from error
    return events


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


def verify(log_path, native_dir, xenos_dir, expected_epochs):
    events = load_events(log_path)
    failures = [
        event
        for event in events
        if event.get("event")
        == "native_renderer.shadow_depth_continuous.fail_closed"
    ]
    require(not failures, "continuous shadow depth failed closed")

    publications = [
        event
        for event in events
        if event.get("event")
        == "native_renderer.shadow_depth_batch.publication"
    ]
    require(
        len(publications) == expected_epochs,
        f"expected {expected_epochs} publications, found {len(publications)}",
    )
    frames = []
    for epoch, publication in enumerate(publications, 1):
        require(
            publication.get("status") == "published_depth_stencil",
            f"publication {epoch} did not publish depth/stencil",
        )
        require(
            publication.get("ownership_mode") == "multi_epoch_fail_closed",
            f"publication {epoch} used an unexpected ownership mode",
        )
        require(
            integer(publication, "publication_epoch") == epoch,
            f"publication epoch {epoch} is out of sequence",
        )
        require(publication.get("color") == "not_bound", "color was published")
        require(
            publication.get("consumer_handoff") == "xenos_rt_dump_retained",
            "Xenos render-target dump was not retained",
        )
        require(
            publication.get("xenos_producer_draws") == "preserved",
            "Xenos producer draws were not preserved",
        )
        require(
            publication.get("xenos_draw_suppression") == "false"
            and publication.get("resolve_suppression") == "false"
            and publication.get("suppression_eligible") == "false",
            "a suppression gate was enabled",
        )
        frames.append(integer(publication, "frame"))
    require(
        all(later > earlier for earlier, later in zip(frames, frames[1:])),
        "publication frames are not strictly increasing",
    )

    summaries = [
        event
        for event in events
        if event.get("event") == "native_renderer.shadow_depth_batch.summary"
    ]
    require(len(summaries) == 1, "expected exactly one shadow-depth summary")
    summary = summaries[0]
    expected_requests = expected_epochs * 80
    expected = {
        "status": "bounded_multi_epoch_complete",
        "ownership_mode": "multi_epoch_fail_closed",
        "continuous_failed_closed": "false",
        "continuous_failure_reason": "none",
        "continuous_limit_reached": "true",
        "request_accounting_complete": "true",
        "batch_accounting_complete": "true",
        "consumer_handoff": "xenos_rt_dump_retained",
        "xenos_draw": "preserved",
        "draw_suppression": "false",
        "suppression_eligible": "false",
    }
    for key, value in expected.items():
        require(summary.get(key) == value, f"summary field {key} != {value}")
    for key in ("batches_started", "batches_completed", "publication_attempts",
                "publications", "continuous_publication_epochs",
                "continuous_max_publication_epochs", "continuous_epoch_limit"):
        require(integer(summary, key) == expected_epochs, f"summary field {key} mismatch")
    for key in ("requests", "recorded"):
        require(integer(summary, key) == expected_requests, f"summary field {key} mismatch")
    for key in ("batches_interrupted", "backend_failed_batches",
                "target_creation_failures", "unsupported",
                "publication_failures"):
        require(integer(summary, key) == 0, f"summary field {key} is nonzero")

    native = load_json(native_dir / "readback.json")
    xenos = load_json(xenos_dir / "readback.json")
    require(native.get("capture_role") == "native_batch", "invalid native role")
    require(xenos.get("capture_role") == "xenos_batch", "invalid Xenos role")
    require(native.get("source") == xenos.get("source"), "readback metadata differs")
    require(
        native.get("safety", {}).get("suppression_allowed") is False
        and xenos.get("safety", {}).get("suppression_allowed") is False,
        "readback suppression safety differs",
    )
    native_payload = native_dir / "isolated.bin"
    xenos_payload = xenos_dir / "isolated.bin"
    require(native_payload.is_file(), "native payload is missing")
    require(xenos_payload.is_file(), "Xenos payload is missing")
    native_hash = sha256(native_payload)
    xenos_hash = sha256(xenos_payload)
    require(native_hash == xenos_hash, "native and Xenos payload hashes differ")
    require(
        native_payload.stat().st_size == xenos_payload.stat().st_size,
        "native and Xenos payload sizes differ",
    )
    return {
        "status": "qualified",
        "epochs": expected_epochs,
        "first_frame": frames[0],
        "last_frame": frames[-1],
        "payload_bytes": native_payload.stat().st_size,
        "payload_sha256": native_hash,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--xenos-dir", type=Path, required=True)
    parser.add_argument("--expected-epochs", type=int, default=8)
    arguments = parser.parse_args()
    require(2 <= arguments.expected_epochs <= 120, "expected epochs must be 2..120")
    result = verify(
        arguments.log,
        arguments.native_dir,
        arguments.xenos_dir,
        arguments.expected_epochs,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
