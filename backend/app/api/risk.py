"""L5 standalone scoring and server-derived end-to-end evidence."""

import json
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.routes import document_hint
from app.api.uploads import read_images
from app.layers.l5_risk.engine import WeightedRiskEngine, score_risk
from app.schemas.common import LayerResult
from app.schemas.risk import RiskData, RiskInput
from app.screening import ScreeningResult, screen_document

router = APIRouter(prefix="/api/v1", tags=["L5"])


@router.get("/risk/policy")
def policy() -> dict:
    engine = WeightedRiskEngine()
    return {
        "policy": engine.policy.model_dump(),
        "sha256": engine.digest,
        "calibrated": False,
        "scope": "synthetic-development-demo",
    }


@router.post("/risk/score", response_model=LayerResult[RiskData])
def score(inputs: RiskInput) -> LayerResult[RiskData]:
    """Caller-supplied demo evidence; screening uses server-derived layers."""
    return score_risk(inputs)


@router.post(
    "/screening/analyze",
    response_model=ScreeningResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["document", "reference_date"],
                        "properties": {
                            "document": {"type": "string", "format": "binary"},
                            "live": {"type": "string", "format": "binary"},
                            "frames": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "minItems": 1,
                                "maxItems": 12,
                            },
                            "reference_date": {"type": "string", "format": "date"},
                            "document_type": {"type": "string", "default": "unknown"},
                            "photo_region": {
                                "type": "string",
                                "description": "JSON normalized [x,y,w,h]",
                            },
                            "timestamps_ms": {
                                "type": "string",
                                "description": "JSON array for frames",
                            },
                        },
                    }
                }
            },
        }
    },
)
async def analyze(request: Request) -> ScreeningResult:
    return await run_in_threadpool(
        screen_document, *(await screening_arguments(request))
    )


async def screening_arguments(request: Request) -> tuple:
    """Shared bounded parsing for transient and audited screening endpoints."""
    images, values = await read_images(request, max_files=13)
    if (
        set(images) - {"document", "live", "frames"}
        or len(images.get("document", [])) != 1
        or len(images.get("live", [])) > 1
        or ("live" in images and "frames" in images)
    ):
        raise HTTPException(
            422, "One document and optional live OR ordered frames required."
        )
    if set(values) - {
        "reference_date",
        "document_type",
        "photo_region",
        "timestamps_ms",
    }:
        raise HTTPException(422, "Unknown form field.")
    try:
        reference = date.fromisoformat(values["reference_date"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, "Supply reference_date as YYYY-MM-DD.") from exc
    region = json.loads(values["photo_region"]) if "photo_region" in values else None
    timestamps = (
        json.loads(values["timestamps_ms"]) if "timestamps_ms" in values else None
    )
    if "photo_region" in values and region is None:
        raise HTTPException(422, "photo_region cannot be null.")
    if "timestamps_ms" in values and timestamps is None:
        raise HTTPException(422, "timestamps_ms cannot be null.")
    return (
        images["document"][0],
        reference,
        document_hint(values),
        images.get("live", [None])[0],
        region,
        images.get("frames"),
        timestamps,
    )
