"""Synthetic development smoke report; never a biometric accuracy benchmark."""

import json

from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.engine import ModelUnavailable, get_engine
from app.layers.l4_face.liveness import evaluate_liveness
from app.layers.l4_face.synthetic_identity_index import check_synthetic_identity
from app.layers.l4_face.verification import verify_faces
from app.schemas.faces import SyntheticIdentityRequest
from app.settings import ROOT


def main() -> None:
    directory = ROOT / "data" / "synthetic_faces"
    images = {p.stem: decode_image(p.read_bytes()) for p in directory.glob("*.png")}
    if "a_document" not in images:
        raise SystemExit("Run generate_face_fixtures.py first.")
    try:
        get_engine()
    except ModelUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    results = {}
    for scenario, key in [
        ("same_source_transformed", "a_live"),
        ("different_synthetic_face", "b_live"),
        ("no_face", "no_face"),
        ("multiple_faces", "multiple_faces"),
        ("blurred_face", "blurred_a"),
    ]:
        result = verify_faces(images["a_document"], images[key])
        results[scenario] = result.model_dump(mode="json")
        print(
            f"{scenario}: {result.status}; decision={result.data.decision}; "
            f"cosine={result.data.cosine_similarity}"
        )
    results["still_liveness"] = evaluate_liveness([images["a_live"]]).model_dump(
        mode="json"
    )
    results["repeated_frames"] = evaluate_liveness(
        [images["a_live"]] * 5, [0, 100, 200, 300, 400]
    ).model_dump(mode="json")
    for name, claim in [
        ("same_claim", "SYNTHETIC ALPHA"),
        ("changed_claim", "SYNTHETIC ALIAS"),
    ]:
        result = check_synthetic_identity(
            SyntheticIdentityRequest(
                sample_id="synthetic_a",
                claimed_name=claim,
                document_number="DEMO-A001",
            )
        )
        results[name] = result.model_dump(mode="json")
        print(
            f"{name}: {result.status}; duplicate={result.data.duplicate_identity_hit}"
        )
    results["upstream_threshold_false_match"] = verify_faces(
        images["a_document"],
        images["b_live"],
        threshold=0.363,
    ).model_dump(mode="json")
    report = {
        "scope": (
            "Two generated identities; positive pair shares source pixels. "
            "Development smoke test only."
        ),
        "threshold_calibrated": False,
        "biometric_accuracy_metrics": None,
        "results": results,
    }
    destination = ROOT / "reports" / "phase2_smoke.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {destination}")


if __name__ == "__main__":
    main()
