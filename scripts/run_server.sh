#!/usr/bin/env bash
set -euo pipefail
clear
DEFAULT_HOST="127.0.0.1"
DEFAULT_HTTP_PORT="8080"
DEFAULT_SSE_PORT="8081"
DEFAULT_MCP_PATH="mcp"
DEFAULT_SSE_PATH="sse"

JWT_SECRET_DEFAULT="secret"
export JWT_SECRET="${JWT_SECRET:-$JWT_SECRET_DEFAULT}"
export JWT_REQUIRED="true"
export TOKEN="$(uv run python -c "from clinic_mcp_server.auth.jwt_hs256 import JwtHS256; print(JwtHS256('${JWT_SECRET}').generate_demo_token())")" 

echo ""
echo "===================================="
echo "   Clinic MCP Server - Run Script"
echo "===================================="
echo ""
echo "Select transport:"
echo "  1) streamable-http (JWT $JWT_REQUIRED)"
echo "  2) sse             (JWT $JWT_REQUIRED)"
echo "  3) stdio          (no JWT)"
echo ""

read -rp "Enter choice [1-3]: " choice

HOST="${HOST:-$DEFAULT_HOST}"

case "${choice}" in
  1)
    TRANSPORT="streamable-http"
    PORT="${PORT:-$DEFAULT_HTTP_PORT}"
    MCP_PATH="${MCP_PATH:-$DEFAULT_MCP_PATH}"
  
    echo ""
    echo ">>> Starting Clinic MCP server (streamable-http)"
    echo "    URL:  http://${HOST}:${PORT}/${MCP_PATH}"
    echo ""
    exec uv run python -m clinic_mcp_server.main run \
      --transport "${TRANSPORT}" \
      --host "${HOST}" \
      --port "${PORT}"
    ;;

  2)
    TRANSPORT="sse"
    PORT="${PORT:-$DEFAULT_SSE_PORT}"
    SSE_PATH="${SSE_PATH:-$DEFAULT_SSE_PATH}"

    echo ""
    echo ">>> Starting Clinic MCP server (sse)"
    echo "    URL:  http://${HOST}:${PORT}/${SSE_PATH}"
    echo ""
    exec uv run python -m clinic_mcp_server.main run \
      --transport "${TRANSPORT}" \
      --host "${HOST}" \
      --port "${PORT}"
    ;;

  3)
    TRANSPORT="stdio"

    echo ""
    echo ">>> Starting Clinic MCP server (stdio)"
    echo "    JWT:  N/A"
    echo ""
    exec uv run python -m clinic_mcp_server.main \
      --transport "${TRANSPORT}"
    ;;

  *)
    echo "❌ Invalid choice. Must be 1, 2, or 3."
    exit 1
    ;;
esac
