"""L4 schemas separate matching evidence from liveness and identity decisions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FaceObservation(BaseModel):
    box: tuple[float, float, float, float]
    landmarks: list[tuple[float, float]]
    detection_confidence: float = Field(ge=0, le=1)
    width_pixels: int
    height_pixels: int
    laplacian_variance: float
    brightness: float
    quality_ok: bool
    quality_reasons: list[str]


class DetectionData(BaseModel):
    faces: list[FaceObservation] = Field(default_factory=list)
    face_count: int = 0
    detector: str = "yunet-2023mar"


class VerificationData(BaseModel):
    document_face_count: int = 0
    live_face_count: int = 0
    document_face: FaceObservation | None = None
    live_face: FaceObservation | None = None
    cosine_similarity: float | None = Field(default=None, ge=-1, le=1)
    threshold: float = Field(ge=-1, le=1)
    match: bool | None = None
    decision: Literal["match", "non_match", "undetermined"] = "undetermined"
    model: str = "sface-2021dec"
    model_sha256: str | None = None
    threshold_calibrated: bool = False
    threshold_source: str = "synthetic-development-policy-v1"
    liveness_verified: bool = False


class FrameEvidence(BaseModel):
    index: int
    timestamp_ms: float
    face_count: int
    eyes_visible: int | None = None
    quality_ok: bool = False
    same_face_as_first: bool | None = None
    texture_contrast: float | None = None
    periodic_energy_ratio: float | None = None


class LivenessData(BaseModel):
    method: str = "texture-plus-blink-candidate-v1"
    verdict: Literal["inconclusive", "suspicious"] = "inconclusive"
    liveness_score: float | None = None
    spoof_indicator_score: float | None = Field(default=None, ge=0, le=1)
    blink_candidate: bool = False
    repeated_frame_count: int = 0
    frames: list[FrameEvidence] = Field(default_factory=list)
    review_required: bool = True
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Untrained heuristics; not a calibrated presentation-attack model.",
            "Uploaded frames have no trusted live-capture provenance.",
            "A replay may contain blinking; this module never certifies a live person.",
        ]
    )


class SyntheticIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal["synthetic_a", "synthetic_b"]
    claimed_name: str = Field(min_length=11, max_length=80, pattern=r"^SYNTHETIC ")
    document_number: str = Field(min_length=6, max_length=24, pattern=r"^DEMO-")

    @field_validator("claimed_name", "document_number")
    @classmethod
    def normalize(cls, value: str) -> str:
        return " ".join(value.upper().split())


class SyntheticIdentityData(BaseModel):
    scope: str = "bundled-synthetic-fixtures-only"
    duplicate_identity_hit: bool | None = None
    matched_sample_id: str | None = None
    similarity: float | None = None
    reasons: list[str] = Field(default_factory=list)
    backend: str = "faiss.IndexFlatIP"
    embeddings_persisted: bool = False
