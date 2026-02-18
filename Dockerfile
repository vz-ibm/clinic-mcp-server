FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG TRANSPORT=streamable-http
ENV TRANSPORT=${TRANSPORT}

WORKDIR /app

# If you use uv:
RUN pip install -U pip && pip install uv

# Copy project
COPY pyproject.toml ./
COPY src ./src

# Install (choose one approach)
# RUN pip install -U pip && pip install .

# Runtime defaults (override in docker run)
ENV CLINIC_DB_PATH=/data/clinic.db \
    HOST=0.0.0.0 \
    PORT=8080 \
    TRANSPORT=streamable-http

# Make sure the DB dir exists
RUN mkdir -p /data

EXPOSE 8080

# Entrypoint: uses env vars so you can switch protocol without rebuilding
CMD ["sh", "-c", "python -m clinic_mcp_server.main run --transport ${TRANSPORT} --host ${HOST} --port ${PORT}"]
