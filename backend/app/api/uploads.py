"""Size-bounded multipart parsing that never spools images to disk."""

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.settings import MAX_UPLOAD_BYTES

MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
MAX_MULTI_REQUEST_BYTES = 20 * 1024 * 1024 + 64 * 1024


class MemoryMultipartParser(MultiPartParser):
    # The whole stream is capped below this threshold, so rollover cannot occur.
    spool_max_size = MAX_MULTI_REQUEST_BYTES + 1


async def read_images(
    request: Request,
    max_files: int = 2,
    max_request_bytes: int = MAX_MULTI_REQUEST_BYTES,
) -> tuple[dict[str, list[bytes]], dict[str, str]]:
    if not 0 < max_request_bytes <= MAX_MULTI_REQUEST_BYTES:
        raise ValueError("Request cap must fit the in-memory multipart threshold.")
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > max_request_bytes):
        raise HTTPException(413, "Request exceeds the upload limit.")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(415, "Send multipart/form-data with a document image.")

    async def bounded_stream() -> AsyncIterator[bytes]:
        count = 0
        async for chunk in request.stream():
            count += len(chunk)
            if count > max_request_bytes:
                # Parser closes any open in-memory file objects on this exception.
                raise MultiPartException("Request exceeds the upload limit.")
            yield chunk

    try:
        parser = MemoryMultipartParser(
            request.headers,
            bounded_stream(),
            max_files=max_files,
            max_fields=4,
            max_part_size=4096,
        )
        form = await parser.parse()
    except MultiPartException as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        images: dict[str, list[bytes]] = {}
        values: dict[str, str] = {}
        for key, value in form.multi_items():
            if isinstance(value, UploadFile):
                payload = await value.read(MAX_UPLOAD_BYTES + 1)
                if len(payload) > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Image exceeds the 10 MiB limit.")
                images.setdefault(key, []).append(payload)
            else:
                if key in values:
                    raise HTTPException(422, "Duplicate form fields are not allowed.")
                values[key] = value
        return images, values
    finally:
        await form.close()


async def read_upload(request: Request) -> tuple[bytes, dict[str, str]]:
    images, values = await read_images(
        request, max_files=1, max_request_bytes=MAX_REQUEST_BYTES
    )
    if set(images) != {"document"} or len(images["document"]) != 1:
        raise HTTPException(422, "Exactly one document image is required.")
    return images["document"][0], values


def upload_schema(reference_date: bool = False) -> dict:
    properties = {
        "document": {"type": "string", "format": "binary"},
        "document_type": {
            "type": "string",
            "default": "unknown",
            "enum": [
                "passport",
                "visa",
                "id",
                "license",
                "permit",
                "unknown",
            ],
        },
    }
    required = ["document"]
    if reference_date:
        properties["reference_date"] = {"type": "string", "format": "date"}
        required.append("reference_date")
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
