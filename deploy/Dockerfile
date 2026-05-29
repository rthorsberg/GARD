# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# ---------- builder ----------
FROM base AS builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip uv

COPY pyproject.toml README.md ./
COPY gard ./gard
RUN uv pip install --system --no-deps --target /install . \
 && uv pip install --system --target /install \
      "fastapi>=0.115,<0.116" "pydantic>=2.7,<3" "pydantic-settings>=2.4,<3" \
      "sqlalchemy>=2.0,<3" "alembic>=1.13,<2" "psycopg[binary]>=3.2,<4" \
      "mcp>=1.0,<2" "authlib>=1.3,<2" "python-jose[cryptography]>=3.3,<4" \
      "structlog>=24.1,<25" "httpx>=0.27,<1" "uvicorn[standard]>=0.30,<0.40" \
      "uuid7>=0.1,<1" "pyyaml>=6.0,<7" "jsonschema>=4.22,<5" \
      "python-multipart>=0.0.9,<1" \
      "networkx>=3.2,<4"

# ---------- runtime ----------
FROM base AS runtime
RUN useradd --system --uid 10001 --home /app gard
COPY --from=builder /install /usr/local/lib/python3.12/site-packages
COPY gard ./gard
COPY gard-catalog ./gard-catalog
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
# Pre-create the blob root so the Docker named-volume inherits ownership
# from the image directory rather than getting root:root by default.
# F2's LocalFsBlobStore writes via the gard user (uid 10001).
RUN mkdir -p /var/lib/gard/blobs \
 && chmod +x /usr/local/bin/entrypoint.sh \
 && chown -R gard:gard /app /var/lib/gard

USER gard
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
