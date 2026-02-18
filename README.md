# clinic-mcp-server
Demo MCP server with tools to manage clinic appointments

Build : 
uv sync
uv venv




Python-only: use project.scripts → clinic-mcp-server command
RESET : 
python -m clinic_mcp_server.main reset-db --force --seed

Run server:
./scripts/run_server.sh

Tests:  
uv run pytest -q

Docker : 
docker build -t clinic-mcp-http --build-arg TRANSPORT=streamable-http .
docker build -t clinic-mcp-sse  --build-arg TRANSPORT=sse .
