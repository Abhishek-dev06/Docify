"""CPU OpenCV model adapter with integrity checks and serialized mutable state."""

import hashlib
import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from app.schemas.faces import FaceObservation
from app.settings import MAX_IMAGE_PIXELS, ROOT, load_config


class ModelUnavailable(RuntimeError):
    """Model asset is missing, altered, unsupported or unable to initialize."""


class FaceEngine(Protocol):
    model_sha256: str

    def detect(
        self, image: np.ndarray
    ) -> tuple[list[FaceObservation], list[np.ndarray]]: ...

    def embedding(self, image: np.ndarray, row: np.ndarray) -> np.ndarray: ...


def validate_image_array(image: np.ndarray) -> None:
    if (
        not isinstance(image, np.ndarray)
        or image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] != 3
        or min(image.shape[:2]) < 2
        or image.shape[0] * image.shape[1] > MAX_IMAGE_PIXELS
    ):
        raise ValueError("Expected a bounded uint8 BGR image with three channels.")


def normalize_embedding(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(vector))
    if (
        not len(vector)
        or not np.isfinite(vector).all()
        or not np.isfinite(length)
        or length < 1e-8
    ):
        raise ValueError("Invalid or zero-length face embedding.")
    return np.ascontiguousarray(vector / length)


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left, right = normalize_embedding(left), normalize_embedding(right)
    if left.shape != right.shape:
        raise ValueError("Embedding dimensions differ.")
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


class OpenCVFaceEngine:
    def __init__(self, directory: Path, cfg: dict):
        manifest = json.loads((ROOT / "models" / "manifest.json").read_text())
        paths = {}
        for key, asset in manifest.items():
            path = directory / asset["filename"]
            if not path.is_file():
                raise ModelUnavailable(
                    f"Missing {key}; run scripts/download_face_models.py."
                )
            if (
                path.stat().st_size != asset["size"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]
            ):
                raise ModelUnavailable(f"Integrity verification failed for {key}.")
            paths[key] = str(path)
        try:
            self.detector = cv2.FaceDetectorYN.create(
                paths["yunet"],
                "",
                (320, 320),
                cfg["detection_threshold"],
                0.3,
                5000,
                cv2.dnn.DNN_BACKEND_OPENCV,
                cv2.dnn.DNN_TARGET_CPU,
            )
            self.recognizer = cv2.FaceRecognizerSF.create(
                paths["sface"],
                "",
                cv2.dnn.DNN_BACKEND_OPENCV,
                cv2.dnn.DNN_TARGET_CPU,
            )
        except cv2.error as exc:
            raise ModelUnavailable(
                "OpenCV could not initialize the face models."
            ) from exc
        self.model_sha256 = manifest["sface"]["sha256"]
        self.cfg = cfg
        self.lock = threading.RLock()

    def detect(
        self, image: np.ndarray
    ) -> tuple[list[FaceObservation], list[np.ndarray]]:
        validate_image_array(image)
        height, width = image.shape[:2]
        scale = min(1.0, self.cfg["max_detection_dimension"] / max(height, width))
        small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        with self.lock:
            self.detector.setInputSize((small.shape[1], small.shape[0]))
            _, detected = self.detector.detect(small)
        observations, rows = [], []
        if detected is None:
            return observations, rows
        for item in detected:
            row = item.copy()
            row[:14] /= scale
            if not np.isfinite(row).all():
                continue
            x, y, w, h = (float(v) for v in row[:4])
            x1, y1 = max(0, int(x)), max(0, int(y))
            x2, y2 = min(width, int(x + w)), min(height, int(y + h))
            if x2 <= x1 or y2 <= y1:
                continue
            gray = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            brightness = float(gray.mean())
            reasons = []
            if min(w, h) < self.cfg["min_face_size"]:
                reasons.append("FACE_TOO_SMALL")
            if laplacian < self.cfg["min_face_laplacian"]:
                reasons.append("FACE_BLURRED")
            if (
                not self.cfg["min_face_brightness"]
                <= brightness
                <= self.cfg["max_face_brightness"]
            ):
                reasons.append("FACE_LIGHTING")
            if x < 0 or y < 0 or x + w > width or y + h > height:
                reasons.append("FACE_CLIPPED")
            landmarks = row[4:14].reshape(5, 2)
            if (
                (landmarks < 0).any()
                or (landmarks[:, 0] >= width).any()
                or (landmarks[:, 1] >= height).any()
            ):
                reasons.append("LANDMARKS_OUTSIDE_IMAGE")
            observations.append(
                FaceObservation(
                    box=(
                        x1 / width,
                        y1 / height,
                        (x2 - x1) / width,
                        (y2 - y1) / height,
                    ),
                    landmarks=[
                        (float(p[0] / width), float(p[1] / height)) for p in landmarks
                    ],
                    detection_confidence=float(np.clip(row[14], 0, 1)),
                    width_pixels=x2 - x1,
                    height_pixels=y2 - y1,
                    laplacian_variance=round(laplacian, 3),
                    brightness=round(brightness, 3),
                    quality_ok=not reasons,
                    quality_reasons=reasons,
                )
            )
            rows.append(row)
        return observations, rows

    def embedding(self, image: np.ndarray, row: np.ndarray) -> np.ndarray:
        validate_image_array(image)
        with self.lock:
            aligned = self.recognizer.alignCrop(image, row)
            features = self.recognizer.feature(aligned).copy()
        return normalize_embedding(features)


@lru_cache(maxsize=2)
def _cached_engine(
    directory: str, signature: tuple, config_json: str
) -> OpenCVFaceEngine:
    return OpenCVFaceEngine(Path(directory), json.loads(config_json))


def get_engine() -> OpenCVFaceEngine:
    directory = Path(os.getenv("FACE_MODEL_DIR", ROOT / "models")).resolve()
    files = json.loads((ROOT / "models" / "manifest.json").read_text()).values()
    signature = []
    for asset in files:
        path = directory / asset["filename"]
        if not path.is_file():
            raise ModelUnavailable(
                "Face model files missing; run download_face_models.py."
            )
        stat = path.stat()
        signature.append((stat.st_mtime_ns, stat.st_size))
    return _cached_engine(
        str(directory),
        tuple(signature),
        json.dumps(load_config("face_thresholds.yaml"), sort_keys=True),
    )
