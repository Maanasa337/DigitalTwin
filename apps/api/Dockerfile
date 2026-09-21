# Build context: repository root, e.g. docker build -f apps/api/Dockerfile .
# The API imports the local packages (contracts, nlu, xai), so they have to be in the image.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

# WeasyPrint renders the PDF reports (M10) through pango/cairo. Without these the renderer falls
# back to storing HTML, so the report still exists — it is simply not paginated.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8 fonts-inter \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app/apps/api

# The path dependencies must exist before `uv sync` resolves them.
COPY packages/contracts /app/packages/contracts
COPY packages/nlu /app/packages/nlu
COPY packages/xai /app/packages/xai
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app

RUN useradd --system --uid 10001 app \
    && mkdir -p /data/reports /data/celery \
    && chown app /data/reports /data/celery
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=4)"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
