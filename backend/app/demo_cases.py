"""Fictional screening cases shared by UI, evaluation and explicit demo exports."""

import cv2

from app.demo import SyntheticIdentity, generate_document
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.synthetic_identity_index import synthetic_portrait

SCENARIOS = (
    "genuine",
    "dob_altered",
    "photo_replaced",
    "wrong_face",
    "blacklisted",
    "blurred",
)
PHOTO_REGION = (0.75, 0.21, 0.19375, 0.46)


def demo_case(scenario: str) -> tuple[bytes, bytes, dict]:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown synthetic scenario.")
    identity = SyntheticIdentity(
        number="Z9000001" if scenario == "blacklisted" else "Z9000000"
    )
    variant = "dob_altered" if scenario == "dob_altered" else "genuine"
    payload, truth = generate_document(identity, variant)
    image = decode_image(payload)
    portrait = "synthetic_b" if scenario == "photo_replaced" else "synthetic_a"
    image[245:555, 1200:1510] = cv2.resize(synthetic_portrait(portrait), (310, 310))
    if scenario == "blurred":
        image = cv2.GaussianBlur(image, (51, 51), 15)
    live = cv2.resize(
        synthetic_portrait(
            "synthetic_b" if scenario == "wrong_face" else "synthetic_a"
        ),
        (600, 600),
    )
    return (
        cv2.imencode(".png", image)[1].tobytes(),
        cv2.imencode(".png", live)[1].tobytes(),
        {**truth, "scenario": scenario, "photo_region": PHOTO_REGION},
    )
