FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg curl ca-certificates && rm -rf /var/lib/apt/lists/* \
 && curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=/opt >/dev/null && ln -s /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY docs ./docs
RUN uv sync --frozen --no-dev
# mcp-clickhouse needs mcp 2.x; the app needs mcp 1.x for ADK — keep them in separate environments.
RUN UV_TOOL_BIN_DIR=/usr/local/bin uv tool install mcp-clickhouse
ENV PATH="/app/.venv/bin:$PATH" SCRIPTY_FRAMES_DIR=/app/data/frames
EXPOSE 8080
CMD ["uvicorn", "scripty.app:app", "--host", "0.0.0.0", "--port", "8080"]
