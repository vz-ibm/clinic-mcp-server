FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv
RUN pip install -U pip && pip install uv

# Copy dependency metadata first for caching
COPY pyproject.toml uv.lock README.md ./

# Create venv + install deps
RUN uv venv && uv sync --frozen --no-dev

# Copy source after deps (better caching)
COPY src ./src

# Install your package into the venv
RUN uv pip install .

# Runtime defaults
ENV CLINIC_DB_PATH=/data/clinic.db \
    HOST=0.0.0.0 \
    PORT=8080 \
    TRANSPORT=streamable-http

RUN mkdir -p /data
EXPOSE 8080

CMD ["sh", "-c", "uv run python -m clinic_mcp_server.main run --transport ${TRANSPORT} --host ${HOST} --port ${PORT}"]
