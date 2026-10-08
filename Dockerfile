# syntax=docker/dockerfile:1
FROM node:22.18-bookworm-slim AS dashboard
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    TESSERACT_CMD=/usr/bin/tesseract OCR_LANGUAGE=eng \
    SCREENING_DATABASE_URL=sqlite:////app/data/screening.db \
    AUDIT_DATABASE_URL=sqlite:////app/data/audit.db FACE_MODEL_DIR=/app/models
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng fonts-dejavu-core libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY backend/ ./backend/
RUN python -m pip install -e './backend[face]'
ARG WITH_TORCH=1
RUN if [ "$WITH_TORCH" = "1" ]; then python -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu; fi
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY assets/ ./assets/
COPY models/ ./models/
COPY --from=dashboard /build/dist ./frontend/dist/
RUN mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["sh", "-c", "python scripts/bootstrap.py && exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
