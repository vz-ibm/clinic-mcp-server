from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Tuple, Optional

import httpx
import json


# ============================================================
# Public API
# ============================================================

def export_mcp_tools_as_openapi(cfg: "ExportConfig") -> Dict[str, Any]:
    """
    Pure OpenAPI 3.1 export:
      - Operations with summary/description
      - Request/response schemas
      - ALL schemas moved into components.schemas and referenced via $ref
    """
    tools = _fetch_tools(cfg)

    paths: dict[str, Any] = {}
    components_schemas: dict[str, Any] = {}

    for tool in tools:
        tool_name = _pick_mcp_tool_name(tool)
        tool_desc = _pick_tool_description(tool)
        summary = _pick_tool_summary(tool)

        # Build/normalize schemas
        input_schema = _normalize_schema(_pick_input_schema(tool))
        input_schema = _merge_param_descriptions_into_schema(schema=input_schema, tool=tool)

        output_schema, output_found = _pick_output_schema(tool)
        if output_found:
            output_schema = _normalize_schema(output_schema)
            output_schema = _merge_result_descriptions_into_schema(schema=output_schema, tool=tool)
        else:
            # OpenAPI 3.1 "any"
            output_schema = {}

        # Move to components + $ref
        req_schema_name = _schema_name(tool_name, "Request")
        resp_schema_name = _schema_name(tool_name, "Response")

        components_schemas[req_schema_name] = input_schema
        components_schemas[resp_schema_name] = output_schema

        req_ref = {"$ref": f"#/components/schemas/{req_schema_name}"}
        resp_ref = {"$ref": f"#/components/schemas/{resp_schema_name}"}

        route = f"/tools/{tool_name}"
        paths[route] = {
            "post": {
                "operationId": _safe_operation_id(tool_name),
                "summary": summary or tool_name,
                "description": (tool_desc or "").strip(),
                "tags": ["mcp-tools"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": req_ref}},
                },
                "responses": {
                    "200": {
                        "description": _pick_output_description(tool),
                        "content": {"application/json": {"schema": resp_ref}},
                    }
                },
            }
        }

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": cfg.title,
            "version": cfg.version,
            "description": (
                "OpenAPI export of MCP tools metadata. "
                "Contains only operation descriptions and input/output schemas to support code generation. "
                "All schemas are defined in components.schemas and referenced via $ref."
            ),
        },
        "paths": paths,
        "tags": [{"name": "mcp-tools"}],
        "components": {"schemas": components_schemas},
        "x-generated-at": datetime.now(timezone.utc).isoformat(),
    }
    return spec


def export_mcp_tools_as_openapi_json_file(cfg: "ExportConfig", out_path: str | Path) -> Path:
    spec = export_mcp_tools_as_openapi(cfg)

    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out_path


# ============================================================
# Configuration
# ============================================================

@dataclass(frozen=True)
class ExportConfig:
    title: str = "MCP Tools"
    version: str = "0.1.0"

    gateway_tools_url: str = ""
    mcp_url: str = ""
    mcp_session_id: str = ""
    bearer_token: str = ""
    timeout_s: float = 30.0


# ============================================================
# Fetch Tools
# ============================================================

def _fetch_tools(cfg: ExportConfig) -> list[dict[str, Any]]:
    if cfg.gateway_tools_url:
        return _fetch_tools_from_gateway(cfg.gateway_tools_url, cfg.bearer_token, cfg.timeout_s)
    if cfg.mcp_url:
        return _fetch_tools_from_mcp(cfg)
    raise ValueError("Provide either gateway_tools_url or mcp_url")


def _fetch_tools_from_gateway(url: str, bearer_token: str, timeout_s: float) -> list[dict[str, Any]]:
    headers = _auth_headers(bearer_token)
    with httpx.Client(headers=headers, timeout=timeout_s, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, list):
        raise TypeError(f"Expected list from {url}, got {type(payload)}")
    return payload


def _fetch_tools_from_mcp(cfg: ExportConfig) -> list[dict[str, Any]]:
    session_id = cfg.mcp_session_id or _mcp_initialize(cfg.mcp_url, cfg.bearer_token, cfg.timeout_s)

    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    headers = _mcp_headers(cfg.bearer_token, session_id)

    with httpx.Client(timeout=cfg.timeout_s, follow_redirects=True) as client:
        r = client.post(cfg.mcp_url, headers=headers, json=req)
        r.raise_for_status()
        result = _parse_mcp_jsonrpc_response(r)

    tools = result.get("tools")
    if not isinstance(tools, list):
        raise TypeError(f"Expected result.tools list from MCP tools/list, got {type(tools)}")

    return [_normalize_mcp_tool(t) for t in tools]


def _mcp_initialize(mcp_url: str, bearer_token: str, timeout_s: float) -> str:
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "openapi-exporter", "version": "0"},
        },
    }
    headers = _mcp_headers(bearer_token, None)
    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        r = client.post(mcp_url, headers=headers, json=req)
        r.raise_for_status()
        result = _parse_mcp_jsonrpc_response(r)

    sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id") or ""
    if not sid:
        sid = (
            result.get("sessionId")
            or result.get("session_id")
            or result.get("mcpSessionId")
            or ""
        )
    if not sid:
        raise RuntimeError("Could not determine MCP session id; provide mcp_session_id explicitly.")
    return sid


def _parse_mcp_jsonrpc_response(resp: httpx.Response) -> dict[str, Any]:
    ctype = (resp.headers.get("content-type") or "").lower()

    if "text/event-stream" in ctype:
        envelope: Optional[dict[str, Any]] = None
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                raw = line[len("data:") :].strip()
                try:
                    obj = httpx.Response(200, content=raw).json()
                except Exception:
                    continue
                if isinstance(obj, dict):
                    envelope = obj
        if envelope is None:
            raise RuntimeError("Failed to parse SSE response (no JSON data lines).")
    else:
        envelope = resp.json()

    if not isinstance(envelope, dict):
        raise TypeError(f"Expected JSON-RPC envelope dict, got {type(envelope)}")

    if envelope.get("error"):
        raise RuntimeError(f"MCP JSON-RPC error: {envelope['error']}")

    result = envelope.get("result")
    if not isinstance(result, dict):
        raise TypeError(f"Expected envelope.result dict, got {type(result)}")

    return result


def _normalize_mcp_tool(t: dict[str, Any]) -> dict[str, Any]:
    out = dict(t)
    out.setdefault("displayName", out.get("name"))
    out.setdefault("originalName", out.get("name"))
    out.setdefault("id", out.get("name"))
    return out


# ============================================================
# Metadata pickers
# ============================================================

def _pick_mcp_tool_name(tool: dict[str, Any]) -> str:
    return tool.get("name") or "unknown-tool"


def _pick_tool_description(tool: dict[str, Any]) -> str:
    return tool.get("description") or tool.get("summary") or ""


def _pick_output_description(tool: dict[str, Any]) -> str:
    return tool.get("outputDescription") or tool.get("resultDescription") or "Tool result"


def _pick_input_schema(tool: dict[str, Any]) -> dict[str, Any]:
    for key in ("inputSchema", "input_schema", "parameters", "schema"):
        schema = tool.get(key)
        if isinstance(schema, dict) and schema:
            return dict(schema)
    return {"type": "object", "additionalProperties": True}


def _pick_output_schema(tool: dict[str, Any]) -> Tuple[dict[str, Any], bool]:
    for key in (
        "outputSchema",
        "output_schema",
        "responseSchema",
        "response_schema",
        "returnSchema",
        "return_schema",
        "resultSchema",
        "result_schema",
    ):
        schema = tool.get(key)
        if isinstance(schema, dict) and schema:
            return dict(schema), True
    return {}, False


def _pick_tool_summary(tool: dict[str, Any]) -> str:
    text = (tool.get("description") or tool.get("summary") or "").strip()
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    m = re.search(r"[.!?]\s", text)
    if not m:
        return text
    return text[: m.end() - 1].strip()


# ============================================================
# Schema normalization & enrichment
# ============================================================

def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    s = dict(schema or {})
    s.pop("$schema", None)
    if "type" not in s and isinstance(s.get("properties"), dict):
        s["type"] = "object"
    return s


def _merge_param_descriptions_into_schema(schema: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    s = dict(schema or {})
    if s.get("type") != "object":
        return s

    props = s.get("properties")
    if not isinstance(props, dict):
        props = {}
        s["properties"] = props

    candidates = (
        tool.get("params"),
        tool.get("parameters"),
        tool.get("inputParameters"),
        tool.get("arguments"),
    )

    for cand in candidates:
        if isinstance(cand, list):
            for item in cand:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                prop = props.get(name)
                if not isinstance(prop, dict):
                    prop = {}
                    props[name] = prop
                if "description" not in prop and item.get("description"):
                    prop["description"] = str(item["description"])
                item_schema = item.get("schema")
                if isinstance(item_schema, dict) and item_schema:
                    for k, v in _normalize_schema(item_schema).items():
                        prop.setdefault(k, v)

        elif isinstance(cand, dict):
            for name, item in cand.items():
                if not name:
                    continue
                prop = props.get(name)
                if not isinstance(prop, dict):
                    prop = {}
                    props[name] = prop
                if isinstance(item, dict):
                    if "description" not in prop and item.get("description"):
                        prop["description"] = str(item["description"])
                    item_schema = item.get("schema")
                    if isinstance(item_schema, dict) and item_schema:
                        for k, v in _normalize_schema(item_schema).items():
                            prop.setdefault(k, v)

    return s


def _merge_result_descriptions_into_schema(schema: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    s = dict(schema or {})
    if s.get("type") != "object":
        return s

    props = s.get("properties")
    if not isinstance(props, dict):
        props = {}
        s["properties"] = props

    candidates = (
        tool.get("outputFields"),
        tool.get("outputParameters"),
        tool.get("resultFields"),
        tool.get("result"),
    )

    for cand in candidates:
        if isinstance(cand, list):
            for item in cand:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                prop = props.get(name)
                if not isinstance(prop, dict):
                    prop = {}
                    props[name] = prop
                if "description" not in prop and item.get("description"):
                    prop["description"] = str(item["description"])
                item_schema = item.get("schema")
                if isinstance(item_schema, dict) and item_schema:
                    for k, v in _normalize_schema(item_schema).items():
                        prop.setdefault(k, v)

        elif isinstance(cand, dict):
            for name, item in cand.items():
                if not name:
                    continue
                prop = props.get(name)
                if not isinstance(prop, dict):
                    prop = {}
                    props[name] = prop
                if isinstance(item, dict):
                    if "description" not in prop and item.get("description"):
                        prop["description"] = str(item["description"])
                    item_schema = item.get("schema")
                    if isinstance(item_schema, dict) and item_schema:
                        for k, v in _normalize_schema(item_schema).items():
                            prop.setdefault(k, v)

    return s


# ============================================================
# Components schema naming
# ============================================================

def _schema_name(tool_name: str, suffix: str) -> str:
    """
    Create a stable components.schemas name from tool_name.
    Keeps readability but avoids illegal JSON Pointer chars.
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", tool_name).strip("_")
    if not base:
        base = "Tool"
    return f"{base}{suffix}"


# ============================================================
# Misc helpers
# ============================================================

def _auth_headers(token: str) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _mcp_headers(token: str, session_id: Optional[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json, text/event-stream"
    if session_id:
        headers["mcp-session-id"] = session_id
    return headers


def _safe_operation_id(tool_name: str) -> str:
    return tool_name


# ============================================================
# Example usage
# ============================================================

if __name__ == "__main__":
    cfg = ExportConfig(
        mcp_url="http://127.0.0.1:8080/mcp",
        bearer_token="",
        mcp_session_id="",
        title="My MCP Tools (Direct)",
        version="1.0.0",
    )

    out_file = export_mcp_tools_as_openapi_json_file(cfg, "./out/mcp_tools_openapi_direct.json")
    print(f"Wrote OpenAPI JSON to: {out_file}")
