# Build context: repository root, e.g. docker build -f apps/edge/Dockerfile .
# The same image runs on a Raspberry Pi 4/5 (linux/arm64): every dependency ships arm64 wheels.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /usr/local/bin/uv

# LightGBM's native library needs the OpenMP runtime.
RUN apt-get update && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app/apps/edge

# The path dependencies must exist before `uv sync` resolves them.
COPY packages/contracts /app/packages/contracts
COPY packages/pdm /app/packages/pdm
COPY packages/xai /app/packages/xai
COPY apps/edge/pyproject.toml apps/edge/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/edge/edge ./edge
RUN uv sync --frozen --no-dev

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin edge \
    && mkdir -p /edge \
    && chown edge /edge
USER edge

ENV PATH="/app/apps/edge/.venv/bin:${PATH}" \
    EDGE_MODEL_DIR=/models \
    EDGE_BUFFER_PATH=/edge/buffer.sqlite \
    EDGE_LOG_PATH=/edge/latency.csv \
    NUMBA_CACHE_DIR=/tmp/numba \
    MPLCONFIGDIR=/tmp/matplotlib

CMD ["python", "-m", "edge"]
