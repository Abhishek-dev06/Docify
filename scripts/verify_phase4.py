"""Real synthetic end-to-end smoke runs; not an accuracy or throughput benchmark."""

import json
from datetime import date

import cv2
from app.demo import SyntheticIdentity, generate_document
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.synthetic_identity_index import (
    check_synthetic_identity,
    synthetic_portrait,
)
from app.layers.l5_risk.engine import score_risk
from app.layers.l5_risk.evidence import risk_inputs
from app.schemas.faces import SyntheticIdentityRequest
from app.schemas.risk import RiskInput, RiskSignal
from app.screening import screen_document
from app.settings import ROOT, load_config
from app.storage.database import seed_mock_database
from demo_phase4 import compact_result


def document(variant="genuine", number="Z9000000") -> bytes:
    image = decode_image(
        generate_document(SyntheticIdentity(number=number), variant)[0]
    )
    image[245:555, 1200:1510] = cv2.resize(
        synthetic_portrait("synthetic_a"), (310, 310)
    )
    if variant == "blurred":
        image = cv2.GaussianBlur(image, (51, 51), 15)
    return cv2.imencode(".png", image)[1].tobytes()


def main() -> None:
    data_dir = ROOT / "data" / "phase4"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{(data_dir / 'mock.db').as_posix()}"
    seed_mock_database(db_url)
    reports = {}
    scenarios = [
        ("genuine_synthetic", "genuine", "Z9000000", "synthetic_a"),
        ("dob_altered", "dob_altered", "Z9000000", "synthetic_a"),
        ("wrong_synthetic_face", "genuine", "Z9000000", "synthetic_b"),
        ("mock_blacklist", "genuine", "Z9000001", "synthetic_a"),
        ("blurred", "blurred", "Z9000000", "synthetic_a"),
    ]
    for name, variant, number, portrait in scenarios:
        payload = document(variant, number)
        live = cv2.imencode(
            ".png", cv2.resize(synthetic_portrait(portrait), (600, 600))
        )[1].tobytes()
        result = screen_document(
            payload,
            date(2026, 10, 3),
            "passport",
            live,
            (1200 / 1600, 210 / 1000, 310 / 1600, 460 / 1000),
            db_url=db_url,
        )
        reports[name] = compact_result(result)
        print(
            f"{name}: status={result.status}, score={result.risk.data.score}, "
            f"category={result.risk.data.category}, total={result.duration_ms}ms, "
            f"parallel={result.parallel_stage_ms}ms",
            flush=True,
        )
    controlled = {}
    for name, active in [
        ("all_supplied_clean", None),
        ("face_nonmatch", "face"),
        ("blacklist", "blacklist"),
    ]:
        inputs = RiskInput(
            signals={
                n: RiskSignal(
                    value=float(n == active),
                    complete=True,
                    explanation="Controlled arithmetic example; not measured evidence.",
                    source="test fixture",
                )
                for n in load_config("risk_weights.yaml")["weights"]
            }
        )
        controlled[name] = score_risk(inputs).model_dump(mode="json")
    duplicate = check_synthetic_identity(
        SyntheticIdentityRequest(
            sample_id="synthetic_a",
            claimed_name="SYNTHETIC ALIAS",
            document_number="DEMO-X999",
        )
    )
    output = {
        "scope": "synthetic smoke; not held-out accuracy",
        "pipeline": reports,
        "controlled_policy_examples": controlled,
        "synthetic_duplicate": score_risk(risk_inputs(duplicate=duplicate)).model_dump(
            mode="json"
        ),
    }
    (ROOT / "reports" / "phase4_smoke.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
