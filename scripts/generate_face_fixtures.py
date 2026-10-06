"""Build labeled synthetic CV fixtures from the bundled generated contact sheet."""

import json

import cv2
import numpy as np
from app.demo import generate_document
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.synthetic_identity_index import synthetic_portrait
from app.settings import ROOT


def main() -> None:
    output = ROOT / "data" / "synthetic_faces"
    output.mkdir(parents=True, exist_ok=True)
    a = synthetic_portrait("synthetic_a")
    b = synthetic_portrait("synthetic_b")
    document = decode_image(generate_document()[0])
    document[245:555, 1200:1510] = cv2.resize(a, (310, 310))
    cv2.putText(
        document,
        "SYNTHETIC A",
        (1205, 610),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (25, 45, 60),
        2,
    )
    live = cv2.resize(a, (600, 600))
    rotation = cv2.getRotationMatrix2D((300, 300), 2.0, 1.0)
    live = cv2.warpAffine(live, rotation, (600, 600), borderMode=cv2.BORDER_REFLECT)
    live = cv2.convertScaleAbs(live, alpha=0.95, beta=7)
    fixtures = {
        "a_document": document,
        "a_live": live,
        "b_live": cv2.resize(b, (600, 600)),
        "multiple_faces": np.concatenate(
            [cv2.resize(a, (600, 600)), cv2.resize(b, (600, 600))], axis=1
        ),
        "no_face": np.full((600, 600, 3), 180, dtype=np.uint8),
        "blurred_a": cv2.GaussianBlur(live, (71, 71), 20),
    }
    for name, image in fixtures.items():
        if not cv2.imwrite(str(output / f"{name}.png"), image):
            raise RuntimeError("Failed to write synthetic fixture.")
    truth = {
        "synthetic": True,
        "source": "assets/synthetic_faces.png (built-in image generation)",
        "positive_pair": ["a_document.png", "a_live.png"],
        "negative_pair": ["a_document.png", "b_live.png"],
        "limitation": (
            "Positive pair shares source pixels; not independent captures. "
            "No FAR/FRR or live-person claims."
        ),
    }
    (output / "manifest.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Six synthetic face fixtures written to {output}")


if __name__ == "__main__":
    main()
