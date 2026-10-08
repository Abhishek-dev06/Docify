"""L4 REST adapters with in-memory, bounded multipart uploads."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.uploads import read_images
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l4_face.engine import ModelUnavailable, get_engine
from app.layers.l4_face.liveness import evaluate_liveness
from app.layers.l4_face.synthetic_identity_index import check_synthetic_identity
from app.layers.l4_face.verification import detect_faces, verify_faces
from app.schemas.common import LayerResult
from app.schemas.faces import (
    DetectionData,
    LivenessData,
    SyntheticIdentityData,
    SyntheticIdentityRequest,
    VerificationData,
)

router = APIRouter(prefix="/api/v1", tags=["L4"])


@router.get("/faces/status")
def model_status() -> dict:
    try:
        engine = get_engine()
        return {
            "status": "ok",
            "backend": "opencv-cpu",
            "recognizer": "sface-2021dec",
            "sha256": engine.model_sha256,
        }
    except ModelUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}


def face_upload_schema(mode: str) -> dict:
    binary = {"type": "string", "format": "binary"}
    if mode == "verify":
        properties = {
            "document": binary,
            "live": binary,
            "threshold": {"type": "number", "minimum": -1, "maximum": 1},
        }
        required = ["document", "live"]
    elif mode == "liveness":
        properties = {
            "frames": {"type": "array", "items": binary, "minItems": 1, "maxItems": 12},
            "timestamps_ms": {
                "type": "string",
                "description": "JSON array, e.g. [0,100,200,300,400]",
            },
        }
        required = ["frames"]
    else:
        properties, required = {"image": binary}, ["image"]
    return {
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                }
            },
        }
    }


def require_files(images: dict[str, list[bytes]], keys: set[str]) -> None:
    if set(images) != keys or any(len(images[key]) != 1 for key in keys):
        raise HTTPException(422, "Exactly one file per required image field is needed.")


@router.post(
    "/faces/detect",
    response_model=LayerResult[DetectionData],
    openapi_extra=face_upload_schema("detect"),
)
async def detection(request: Request) -> LayerResult[DetectionData]:
    images, _ = await read_images(request, max_files=1)
    require_files(images, {"image"})
    return await run_in_threadpool(
        lambda: detect_faces(decode_image(images["image"][0]))
    )


@router.post(
    "/faces/verify",
    response_model=LayerResult[VerificationData],
    openapi_extra=face_upload_schema("verify"),
)
async def verification(request: Request) -> LayerResult[VerificationData]:
    images, values = await read_images(request)
    require_files(images, {"document", "live"})
    threshold = float(values["threshold"]) if "threshold" in values else None
    return await run_in_threadpool(
        lambda: verify_faces(
            decode_image(images["document"][0]),
            decode_image(images["live"][0]),
            threshold,
        )
    )


@router.post(
    "/faces/liveness",
    response_model=LayerResult[LivenessData],
    openapi_extra=face_upload_schema("liveness"),
)
async def liveness(request: Request) -> LayerResult[LivenessData]:
    images, values = await read_images(request, max_files=12)
    if set(images) != {"frames"}:
        raise HTTPException(422, "Use the frames field for ordered images.")
    times = json.loads(values["timestamps_ms"]) if "timestamps_ms" in values else None
    if times is not None and (
        not isinstance(times, list)
        or any(isinstance(t, bool) or not isinstance(t, (int, float)) for t in times)
    ):
        raise ValueError("timestamps_ms must be a JSON array of numbers.")

    def process() -> LayerResult[LivenessData]:
        frames = []
        total_pixels = 0
        for payload in images["frames"]:
            frame = decode_image(payload)
            total_pixels += frame.shape[0] * frame.shape[1]
            if total_pixels > 12_000_000:
                raise ValueError("Total frame pixel count exceeds the sequence limit.")
            frames.append(frame)
        return evaluate_liveness(frames, times)

    return await run_in_threadpool(process)


@router.post(
    "/demo/identities/check", response_model=LayerResult[SyntheticIdentityData]
)
def synthetic_identity(
    request: SyntheticIdentityRequest,
) -> LayerResult[SyntheticIdentityData]:
    return check_synthetic_identity(request)
