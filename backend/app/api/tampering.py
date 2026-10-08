"""L3 multipart adapter; no image or EXIF persistence."""

import json

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.uploads import read_upload
from app.layers.l3_tampering.analyzer import analyze_tampering
from app.layers.l3_tampering.classical import validate_region
from app.schemas.common import LayerResult
from app.schemas.tampering import TamperingData

router = APIRouter(prefix="/api/v1/tampering", tags=["L3"])


@router.post(
    "/analyze",
    response_model=LayerResult[TamperingData],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["document"],
                        "properties": {
                            "document": {"type": "string", "format": "binary"},
                            "photo_region": {
                                "type": "string",
                                "description": "JSON [x,y,w,h], normalized",
                            },
                            "include_cnn": {"type": "boolean", "default": True},
                        },
                    }
                }
            },
        }
    },
)
async def analyze(request: Request) -> LayerResult[TamperingData]:
    payload, values = await read_upload(request)
    if set(values) - {"photo_region", "include_cnn"}:
        raise HTTPException(422, "Unknown form field.")
    region = None
    if "photo_region" in values:
        region = validate_region(json.loads(values["photo_region"]))
    enabled = values.get("include_cnn", "true").lower()
    if enabled not in {"true", "false"}:
        raise HTTPException(422, "include_cnn must be true or false.")
    return await run_in_threadpool(
        lambda: analyze_tampering(payload, region, enabled == "true")
    )
