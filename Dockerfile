# syntax=docker/dockerfile:1.7
#
# IPO Engine API (FastAPI). Two stages: the builder installs the locked dependencies and the package
# into a virtualenv; the runtime image copies only that virtualenv. Base images are pinned by digest;
# Dependabot (docker ecosystem) proposes updates.
#
#   docker build -t ipo-engine .
#   docker run --rm -p 8000:8000 -v ipo-data:/data -e API_KEYS=... ipo-engine
#
# The only writable path is /data (plus a tmpfs /tmp if the root filesystem is read-only).
#
# The image runs in production mode, which REFUSES TO START without API keys: pass -e API_KEYS=...
# (digests from `ipo keys hash`), or -e ALLOW_UNAUTHENTICATED=true to run open on purpose.

# python:3.12-slim (multi-arch index)
ARG PYTHON_IMAGE=python:3.12-slim@sha256:a0e2dd78cc679ddfffea960fe45ecfcff9ac2f68d67917a0edfcde5c2100151b
# uv 0.11.32, the version CI and the lockfile use
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first, so source edits do not re-resolve them. --frozen: exactly what uv.lock says.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/ipo_due_diligence.db

# Tesseract (English + orientation data) is used only for the OCR fallback on scanned pages.
# `upgrade` first: the base image is pinned by digest, so Debian security fixes published after the
# pin (for example libzstd1, CVE-2026-124851) would otherwise stay in the image until the next bump.
RUN apt-get update \
    && apt-get -y --no-install-recommends upgrade \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --user-group --no-create-home --home-dir /nonexistent app \
    && mkdir -p /data && chown 10001:10001 /data

COPY --from=builder /opt/venv /opt/venv

USER 10001:10001
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "ipo_engine.screening.main:app", "--host", "0.0.0.0", "--port", "8000"]
