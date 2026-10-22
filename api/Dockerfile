# Imagen del api de APEX (US-005). Dos etapas: builder con uv, runtime slim sin
# compiladores, sin grupo dev y con usuario apex (UID 10001). La misma imagen sirve
# para api, worker y tools con comandos distintos. Nunca contiene .env ni llaves.

# python:3.12-slim por digest (2026-10-22, S3-D62); renovar (docs/RUNBOOK.md §7):
# docker buildx imagetools inspect python:3.12-slim --format '{{json .Manifest.Digest}}'
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_NO_CACHE_DIR=1
# uv se instala desde PyPI (misma versión que en desarrollo); evita depender de ghcr.io.
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /app
# Capa de dependencias, cacheable mientras no cambien pyproject.toml ni uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# Código, migraciones y configuración de Alembic (B-3: la imagen migra al arrancar).
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# Mismo digest que builder (2026-10-22); renovar:
# docker buildx imagetools inspect python:3.12-slim --format '{{json .Manifest.Digest}}'
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 AS runtime
# SHA corto de git que publica /health como `version` (US-020).
ARG GIT_SHA=dev
ENV APP_VERSION=$GIT_SHA
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 apex \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin apex \
    && mkdir -p /run/apex/keys /data/uploads \
    && chown -R apex:apex /run/apex /data
COPY --from=builder --chown=apex:apex /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC
USER apex
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
