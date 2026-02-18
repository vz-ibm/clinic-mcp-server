# Clinic MCP Server

Demo MCP server for a clinic scheduling domain (users, payment methods, doctors, slots, appointments) backed by SQLite.

Supports **three transports**:
- **stdio** (local MCP clients / agents)
- **streamable-http**
- **sse**

Supports **JWT authorization** for HTTP transports (configurable).

---

## Project Structure

```
src/clinic_mcp_server/
  main.py                  # entrypoint (supports legacy flags + Typer)
  cli/app.py               # Typer CLI
  runtime/                 # runner + settings + MCP app factory
  auth/                    # HS256 JWT + ASGI middleware
  tools/clinic_server.py   # FastMCP tools
  model/clinic_db.py       # SQLite database implementation
  services/                # domain services
  infra/                   # SQLite repository implementation
  domain/                  # enums, errors, interfaces
tests/
  ...
```

---

# Development

## Prerequisites
- Python **3.12+**
- [`uv`](https://github.com/astral-sh/uv) installed

Check:
```bash
python --version
uv --version
```

---

## Install (dev)

From repo root:

```bash
uv venv
uv sync
```

Recommended dev dependencies:
- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `typer`
- `uvicorn`
- `ruff`
- `pyright`

---

## Run tests

```bash
uv run pytest -q
```

With coverage:
```bash
uv run pytest -q --cov=clinic_mcp_server --cov-report=term-missing
```

---

## Lint / typecheck

### Ruff
```bash
uv run ruff check .
```

Auto-fix:
```bash
uv run ruff check --fix .
```

### Pyright
Install:
```bash
uv add --dev pyright
```

Run:
```bash
uv run pyright
```

---

# Usage via Python package

> The entrypoint supports both **new Typer subcommand style** and **legacy flags** (for backward compatibility).

## 1) Streamable HTTP (recommended)

```bash
uv run python -m clinic_mcp_server.main run \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8080
```
---

## 2) SSE transport

```bash
uv run python -m clinic_mcp_server.main run \
  --transport sse \
  --host 0.0.0.0 \
  --port 8080
```

---

## 3) STDIO transport

```bash
uv run python -m clinic_mcp_server.main run --transport stdio
```

---

## Database location

By default SQLite file is created under:
```
storage/clinic.db
```

Override:
```bash
export CLINIC_DB_PATH="/tmp/clinic.db"
```

---

# JWT Authorization

By default, JWT is **required** for HTTP transports.

On startup, the server prints a **demo token**.
Use it like this:

```
Authorization: Bearer <token>
```

Configure JWT with env vars:

```bash
export JWT_SECRET="dev-secret-change-me"
export JWT_REQUIRED="true"                 # default true for HTTP, false for stdio
export JWT_ALLOWLIST_PATHS="/health"       # endpoints that bypass auth
export JWT_AUDIENCE="clinic"               # optional
export JWT_ISSUER="clinic-mcp"             # optional
```

Disable JWT (not recommended except tests / local):
```bash
export JWT_REQUIRED="false"
```

---

# Docker

## Build image

From repo root (where your Dockerfile is):

```bash
podman build -t clinic-mcp-server:dev .
```

---

## Run (streamable-http)

```bash
podman run --rm -p 8080:8080 \
  -e JWT_SECRET="dev-secret-change-me" \
  -e JWT_REQUIRED="true" \
  -e CLINIC_DB_PATH="/data/clinic.db" \
  -v "$(pwd)/storage:/data" \
  clinic-mcp-server:dev \
  uv run python -m clinic_mcp_server.main run --transport streamable-http --host 0.0.0.0 --port 8080
```

### Persistent DB volume
The above mounts `./storage` from host into the container at `/data`, so the DB persists.

---

## Run (SSE)

```bash
podman run --rm -p 8080:8080 \
  -e JWT_REQUIRED="false" \
  -e CLINIC_DB_PATH="/data/clinic.db" \
  -v "$(pwd)/storage:/data" \
  clinic-mcp-server:dev \
  uv run python -m clinic_mcp_server.main run --transport sse --host 0.0.0.0 --port 8080
```

---

## Run (stdio)
Typically stdio is used locally (not common in Docker)

---

# Notes / Troubleshooting

## “No such option: --transport”
This means you invoked Typer without a command. Use one of:

```bash
python -m clinic_mcp_server.main run --transport streamable-http ...
```
---

## SQLite concurrency
This is a demo. If you expect concurrent writes:
- enable WAL mode
- use connection-per-request
- or migrate to Postgres

---

# License
Demo / internal use.


## Curl cheatsheet (Health + JWT + MCP)

> **Important:** MCP endpoints are **not** regular REST endpoints.  
> For **Streamable HTTP**, you must use **JSON-RPC POST**.  
> For **SSE**, you must first open the SSE stream, then POST JSON-RPC to the returned `/messages/?session_id=...` endpoint.

### Environment variables used in examples

```bash
export TOKEN="YOUR_JWT_TOKEN_HERE"
```

---

# 1) Streamable HTTP (JWT enabled)

Assume:
- Base URL: `http://127.0.0.1:8080`
- MCP endpoint: `/mcp`

### Health (no JWT, if `/health` is allowlisted)

```bash
curl -i http://127.0.0.1:8080/health
```

### Health (with JWT)

```bash
curl -i -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/health
```

### MCP endpoint should reject without JWT

```bash
curl -i http://127.0.0.1:8080/mcp
# expected: 401 Unauthorized
```

### List tools (JSON-RPC) with JWT

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8080/mcp \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

# 2) SSE (JWT enabled)

Assume:
- Base URL: `http://127.0.0.1:8081`
- SSE endpoint: `/sse`

### Health (no JWT, if `/health` is allowlisted)

```bash
curl -i http://127.0.0.1:8081/health
```

### Health (with JWT)

```bash
curl -i -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8081/health
```

### SSE endpoint should reject without JWT

```bash
curl -i -H "Accept: text/event-stream" http://127.0.0.1:8081/sse
# expected: 401 Unauthorized
```

### Connect SSE stream (with JWT)

```bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8081/sse
```

Expected output includes something like:

```text
event: endpoint
data: /messages/?session_id=ac5e39fe0f2c4a7abb2906454d2f499c
```

### Call tools via SSE (POST JSON-RPC to /messages)

Replace the `session_id` with the one you got from the SSE stream:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:8081/messages/?session_id=YOUR_SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

# 3) Stdio

Stdio is designed for **SDK clients**, not curl.

Use the Python MCP client:

```bash
uv run python scripts/simple_client.py
```

---

### Streamable HTTP via curl (JWT enabled)

> Streamable HTTP is  **session-based** in FastMCP.
>
> That means:
> 1. You must call `initialize` first.
> 2. The server returns a session id.
> 3. You must include that session id on every next request using:
>    `mcp-session-id: ...`
>
> Additionally, FastMCP requires this header:
> `Accept: application/json, text/event-stream`

#### Step 0 — set your JWT token

```bash
export TOKEN="YOUR_JWT_TOKEN_HERE"
```

#### Step 1 — initialize session (prints `mcp-session-id` in response headers)

```bash
curl -i \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -X POST http://127.0.0.1:8080/mcp \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"initialize",
    "params":{
      "protocolVersion":"2025-03-26",
      "capabilities":{},
      "clientInfo":{"name":"curl","version":"0"}
    }
  }'
```

<!-- ```bash
SESSION_ID=$(curl -sSI \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -X POST http://127.0.0.1:8080/mcp \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')
export SESSION_ID
echo "SESSION_ID=$SESSION_ID" -->
```

Look for a response header like:

```text
mcp-session-id: XXXXXXXXXX
```

Copy the value or define as export.

```text
export SESSION_ID=XXXXXXXXXX
```

#### Step 2 — list tools (session-based request)

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SESSION_ID" \
  -X POST http://127.0.0.1:8080/mcp \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Expected output:

```json
{"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
```


### SSE via curl (full working example)

> **SSE is a 2-channel flow**:
> 1. You open a long-lived SSE connection (`/sse`) — this is where responses arrive.
> 2. You POST JSON-RPC messages to `/messages/?session_id=...`.
>
> The `/messages` POST usually returns `Accepted`.  
> The **actual response** arrives on the SSE stream as `event: message`.

#### Step 0 — set your JWT token

```bash
export TOKEN="YOUR_JWT_TOKEN_HERE"
```

#### Step 1 — open SSE stream (Terminal 1)

```bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8081/sse
```

Expected output includes:

```text
event: endpoint
data: /messages/?session_id=XXXXXXXX
```

Copy the value or define as export.

```text
export SESSION_ID=XXXXXXXX
```

#### Step 2 — initialize session (Terminal 2)

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:8081/messages/?session_id=$SESSION_ID" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"initialize",
    "params":{
      "protocolVersion":"2025-03-26",
      "capabilities":{},
      "clientInfo":{"name":"curl","version":"0"}
    }
  }'
```

The response will appear in **Terminal 1** as:

```text
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

#### Step 3 — list tools (Terminal 2)

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:8081/messages/?session_id=$SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

The tools list response will appear in **Terminal 1**:

```text
event: message
data: {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
```
