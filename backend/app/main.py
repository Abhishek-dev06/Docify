"""Local synthetic-demo API; bind to loopback until authentication is added."""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.audit import router as audit_router
from app.api.demo import router as demo_router
from app.api.faces import router as face_router
from app.api.risk import router as risk_router
from app.api.routes import router
from app.api.tampering import router as tamper_router
from app.settings import ROOT, allowed_origins
from app.storage.audit import dispose_audit_stores


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    dispose_audit_stores()


app = FastAPI(
    title="Synthetic Document Screening",
    version="0.1.0",
    description=(
        "Phases 1–6: screening, dashboard, audit and synthetic evaluation. "
        "Synthetic demo; liveness heuristics never certify a live person."
    ),
    lifespan=lifespan,
)
origins = allowed_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Officer-ID", "Idempotency-Key"],
    )
app.include_router(router)
app.include_router(face_router)
app.include_router(tamper_router)
app.include_router(risk_router)
app.include_router(audit_router)
app.include_router(demo_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def error_response(
    request: Request, status: int, code: str, message: str
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", "unknown"),
            }
        },
    )


@app.exception_handler(ValueError)
async def invalid_value(request: Request, exc: ValueError) -> JSONResponse:
    return error_response(request, 422, "INVALID_INPUT", str(exc))


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(request, exc.status_code, "REQUEST_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def schema_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo raw identity fields in error responses or log the request payload.
    locations = [".".join(str(x) for x in error["loc"]) for error in exc.errors()]
    return error_response(
        request, 422, "SCHEMA_ERROR", "Invalid fields: " + ", ".join(locations)
    )


# A built Vite dashboard shares the API origin; no wildcard CORS is required.
if (ROOT / "frontend" / "dist").is_dir():
    app.mount(
        "/",
        StaticFiles(directory=ROOT / "frontend" / "dist", html=True),
        name="dashboard",
    )
