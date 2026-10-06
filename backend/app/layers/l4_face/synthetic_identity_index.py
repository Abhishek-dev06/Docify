"""FAISS demo limited to two bundled, generated identities; no enrollment API."""

import time

import cv2
import numpy as np

from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.engine import ModelUnavailable, get_engine, normalize_embedding
from app.schemas.common import Finding, LayerResult
from app.schemas.faces import SyntheticIdentityData, SyntheticIdentityRequest
from app.settings import ROOT, load_config

CATALOG = {
    "synthetic_a": ("SYNTHETIC ALPHA", "DEMO-A001"),
    "synthetic_b": ("SYNTHETIC BETA", "DEMO-B001"),
}


def synthetic_portrait(sample_id: str) -> np.ndarray:
    if sample_id not in CATALOG:
        raise ValueError("Only bundled synthetic sample IDs are allowed.")
    path = ROOT / "assets" / "synthetic_faces.png"
    if not path.is_file():
        raise ModelUnavailable("Bundled synthetic portrait sheet is missing.")
    sheet = decode_image(path.read_bytes())
    half = sheet.shape[1] // 2
    # These are fixed crops of the generated contact sheet, not external uploads.
    return (
        sheet[:, 2 : half - 2].copy()
        if sample_id == "synthetic_a"
        else sheet[:, half + 3 : -2].copy()
    )


def check_synthetic_identity(
    request: SyntheticIdentityRequest,
) -> LayerResult[SyntheticIdentityData]:
    started = time.perf_counter()
    data = SyntheticIdentityData()
    result = LayerResult(data=data)
    try:
        try:
            import faiss
        except ImportError as exc:
            raise ModelUnavailable(
                "Install the optional face extra for FAISS CPU."
            ) from exc
        engine = get_engine()
        keys, vectors = [], []
        for sample_id in CATALOG:
            portrait = synthetic_portrait(sample_id)
            faces, rows = engine.detect(portrait)
            if len(faces) != 1 or not faces[0].quality_ok:
                raise ModelUnavailable(
                    "Synthetic fixture face could not be extracted reliably."
                )
            keys.append(sample_id)
            vectors.append(normalize_embedding(engine.embedding(portrait, rows[0])))
        matrix = np.ascontiguousarray(vectors, dtype=np.float32)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        scores, positions = index.search(
            matrix[keys.index(request.sample_id) : keys.index(request.sample_id) + 1], 1
        )
        score, position = float(scores[0, 0]), int(positions[0, 0])
        if (
            position < 0
            or score < load_config("face_thresholds.yaml")["cosine_threshold"]
        ):
            data.duplicate_identity_hit = False
        else:
            sample = keys[position]
            expected_name, expected_number = CATALOG[sample]
            data.similarity = float(np.clip(score, -1, 1))
            data.matched_sample_id = sample
            if request.claimed_name != expected_name:
                data.reasons.append(
                    "Different synthetic name for the same fixture embedding."
                )
            if request.document_number != expected_number:
                data.reasons.append(
                    "Different demo document number for the same fixture embedding."
                )
            data.duplicate_identity_hit = bool(data.reasons)
        result.findings.append(
            Finding(
                code="SYNTHETIC_INDEX_ONLY",
                explanation=(
                    "Search is restricted to two fixed generated portraits. "
                    "Alias-rule demonstration; no real-world accuracy claim."
                ),
            )
        )
    except (ModelUnavailable, cv2.error) as exc:
        result.status = "unavailable"
        result.findings.append(
            Finding(
                code="SYNTHETIC_INDEX_UNAVAILABLE",
                explanation=str(exc)
                if isinstance(exc, ModelUnavailable)
                else "Face inference failed.",
            )
        )
    result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return result
