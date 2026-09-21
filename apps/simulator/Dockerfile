# Build context: repository root, e.g. docker build -f apps/simulator/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app/apps/simulator

COPY packages/contracts /app/packages/contracts
COPY apps/simulator/pyproject.toml apps/simulator/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/simulator/sim ./sim
RUN uv sync --frozen --no-dev

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin simulator \
    && mkdir -p /data/synthetic \
    && chown simulator /data/synthetic
USER simulator

ENV PATH="/app/apps/simulator/.venv/bin:${PATH}" \
    SIM_EXPORT_DIR=/data/synthetic

EXPOSE 4840 5020 8090
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"SIM_API_PORT\", \"8090\")}/health', timeout=3)"

CMD ["python", "-m", "sim"]
