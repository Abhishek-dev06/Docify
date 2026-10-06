"""Named fictional fixtures generated in memory for the dashboard walkthrough."""

from typing import Literal

from fastapi import APIRouter, Response

from app.demo_cases import demo_case

router = APIRouter(prefix="/api/v1/demo", tags=["Synthetic fixtures"])


@router.get("/fixtures/{scenario}/{kind}")
def fixture(
    scenario: Literal[
        "genuine",
        "dob_altered",
        "photo_replaced",
        "wrong_face",
        "blacklisted",
        "blurred",
    ],
    kind: Literal["document", "live"],
) -> Response:
    document, live, _ = demo_case(scenario)
    return Response(document if kind == "document" else live, media_type="image/png")
