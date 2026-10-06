"""Check a local deployment and retain an external audit checkpoint for restarts."""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
ACTOR = "DEMO-DEPLOY-QA"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response


def write_checkpoint(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def preflight(client) -> dict:
    health = request(client, "GET", "/api/v1/health").json()
    require(health.get("ocr_available") is True, "Tesseract is unavailable.")
    require(health.get("phase", 0) >= 6, "Expected the completed Phase 6 backend.")
    page = request(client, "GET", "/").text
    asset = re.search(r'src="(/assets/[^\"]+\.js)"', page)
    require(asset is not None, "Built dashboard JavaScript was not found.")
    request(client, "GET", asset.group(1))
    require(
        request(client, "GET", "/api/v1/audit/verify").json()["valid"],
        "Existing audit chain is invalid.",
    )
    return health


def model_checks(analysis: dict, require_cnn: bool) -> dict:
    require(not analysis["failures"], "One or more pipeline stages failed.")
    require(
        (analysis.get("ocr") or {}).get("data", {}).get("mrz") is not None,
        "Synthetic MRZ was not extracted.",
    )
    face = analysis.get("face") or {}
    require(
        face.get("data", {}).get("decision") == "match",
        "Synthetic reference face did not match; inspect model availability.",
    )
    tamper = analysis.get("tampering") or {}
    detectors = tamper.get("data", {}).get("detectors", [])
    cnn = next((d for d in detectors if d["name"] == "cnn"), {})
    available = cnn.get("status") == "ok" and cnn.get("score") is not None
    if require_cnn:
        require(available, "Synthetic CNN unavailable; mount weights/install PyTorch.")
    risk = analysis["risk"]["data"]
    require(
        "liveness" in risk["missing_required_signals"],
        "Still-image liveness must remain unverified.",
    )
    return {
        "mrz_extracted": True,
        "face_match": True,
        "cnn_available": available,
        "cnn_required": require_cnn,
        "pipeline_ms": analysis["duration_ms"],
        "risk_score": risk["score"],
        "risk_category": risk["category"],
        "liveness_unverified": True,
    }


def record(client, state: dict, checkpoint: Path) -> dict:
    images = {
        kind: request(client, "GET", f"/api/v1/demo/fixtures/genuine/{kind}").content
        for kind in ("document", "live")
    }
    files = {
        kind: (f"synthetic_{kind}.png", data, "image/png")
        for kind, data in images.items()
    }
    data = {
        "reference_date": "2026-10-03",
        "document_type": "passport",
        "photo_region": "[0.75,0.21,0.19375,0.46]",
    }
    headers = {"X-Officer-ID": ACTOR, "Idempotency-Key": state["scan_request_id"]}
    result = request(
        client, "POST", "/api/v1/scans/analyze", files=files, data=data, headers=headers
    ).json()
    scan = result["scan_event"]
    state.update(scan_id=scan["scan_id"], scan_event_hash=scan["event_hash"])
    write_checkpoint(checkpoint, state)
    analysis = result["analysis"]
    if analysis is None and "models" not in state:
        # Resume an uncertain write without trying to recover discarded images.
        analysis = request(
            client, "POST", "/api/v1/screening/analyze", files=files, data=data
        ).json()
    if analysis is not None:
        state["models"] = model_checks(analysis, state["require_cnn"])
        write_checkpoint(checkpoint, state)
    replay = request(
        client, "POST", "/api/v1/scans/analyze", files=files, data=data, headers=headers
    ).json()
    require(
        replay["replayed"] and replay["analysis"] is None,
        "Scan retry did not return metadata-only replay.",
    )
    require(replay["scan_event"] == scan, "Scan retry changed the recorded event.")
    body = {
        "decision": "secondary_inspection",
        "note": "Synthetic deployment QA: liveness remains incomplete.",
        "expected_event_hash": scan["event_hash"],
        "request_id": state["decision_request_id"],
        "acknowledge_incomplete": False,
    }
    path = f"/api/v1/scans/{scan['scan_id']}/decisions"
    decision = request(client, "POST", path, json=body, headers=headers).json()
    replay_decision = request(client, "POST", path, json=body, headers=headers).json()
    require(replay_decision == decision, "Decision retry changed the recorded event.")
    state.update(
        decision_event_hash=decision["event_hash"],
        anchor_seq=decision["seq"],
        anchor_hash=decision["event_hash"],
        recorded_at=datetime.now(timezone.utc).isoformat(),
        idempotent_scan=True,
        idempotent_decision=True,
    )
    write_checkpoint(checkpoint, state)
    return state


def verify(client, state: dict) -> dict:
    require("anchor_hash" in state, "Checkpoint incomplete; resume with --record.")
    chain = request(
        client,
        "GET",
        "/api/v1/audit/verify",
        params={
            "anchor_seq": state["anchor_seq"],
            "anchor_hash": state["anchor_hash"],
        },
    ).json()
    require(chain["valid"] and chain["anchor_checked"], "Trusted checkpoint mismatch.")
    detail = request(client, "GET", f"/api/v1/scans/{state['scan_id']}").json()
    hashes = {event["event_hash"] for event in detail["events"]}
    require(
        {state["scan_event_hash"], state["decision_event_hash"]} <= hashes,
        "Original scan/decision missing from retained history.",
    )
    return {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "anchor_checked": True,
        "original_events_retained": True,
        "head_seq": chain["head_seq"],
        "head_hash": chain["head_hash"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--allow-missing-cnn", action="store_true")
    args = parser.parse_args()
    url = args.url.rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        parser.error("This synthetic smoke check targets a local HTTP server only.")
    if args.checkpoint.exists():
        state = json.loads(args.checkpoint.read_text())
        require(state["url"] == url, "Use a separate checkpoint for each deployment.")
        require(
            state["require_cnn"] == (not args.allow_missing_cnn),
            "Checkpoint CNN requirement differs; keep the original mode.",
        )
    else:
        require(args.record, "Checkpoint missing; run --record before restart.")
        state = {
            "url": url,
            "scope": "HTTP checks; container runtime is not inferred",
            "require_cnn": not args.allow_missing_cnn,
            "scan_request_id": str(uuid.uuid4()),
            "decision_request_id": str(uuid.uuid4()),
        }
        write_checkpoint(args.checkpoint, state)
    with httpx.Client(base_url=url, timeout=180, trust_env=False) as client:
        state["health"] = preflight(client)
        if args.record:
            state = record(client, state, args.checkpoint)
        state["last_verification"] = verify(client, state)
    write_checkpoint(args.checkpoint, state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, RuntimeError, OSError, ValueError) as exc:
        print(f"Deployment verification failed: {exc}", file=sys.stderr)
        print(
            "Keep the checkpoint and retry the same command after recovery.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
