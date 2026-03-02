# Local Run (SSE) — 2 Terminals

## Terminal 1 — Build + Run Server

### Build image
```bash
podman build -t clinic-mcp-server:dev .
```

### Run container (SSE transport)
```bash
podman run --rm -p 8081:8081 \
  -e JWT_REQUIRED="true" \
  -e CLINIC_DB_PATH="/data/clinic.db" \
  -v "$(pwd)/storage:/data" \
  clinic-mcp-server:dev \
  uv run python -m clinic_mcp_server.main run \
    --transport sse \
    --host 0.0.0.0 \
    --port 8081
```

---

## Terminal 2 — Run Client Example

### 1) Copy token from Terminal 1
Copy/paste the `export TOKEN="..."` line printed by the server (HS256 JWT).

### 2) Activate venv + run SSE client
```bash
source ./venv/bin/activate
uv run python ./examples/simple_sse/sse_client.py
```
