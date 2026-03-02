from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Dict, Tuple, Optional

import httpx


# ============================================================
# Public API
# ============================================================

def export_mcp_tools_as_openapi(cfg: "ExportConfig") -> Dict[str, Any]:
    """
    Pure OpenAPI 3.1 export:
      - Operations with summary/description
      - Request/response schemas
      - Schemas live in components.schemas and are referenced via $ref
      - Common sub-schemas are deduplicated and extracted to top-level once
    """
    tools = _fetch_tools(cfg)

    paths: dict[str, Any] = {}
    components_schemas: dict[str, Any] = {}

    # 1) Create per-tool Request/Response schemas in components
    for tool in tools:
        tool_name = _pick_mcp_tool_name(tool)
        tool_desc = _pick_tool_description(tool)
        summary = _pick_tool_summary(tool)

        input_schema = _normalize_schema(_pick_input_schema(tool))
        input_schema = _merge_param_descriptions_into_schema(schema=input_schema, tool=tool)

        output_schema, output_found = _pick_output_schema(tool)
        if output_found:
            output_schema = _normalize_schema(output_schema)
            output_schema = _merge_result_descriptions_into_schema(schema=output_schema, tool=tool)
        else:
            output_schema = {}  # OpenAPI 3.1 "any"

        req_schema_name = _schema_name(tool_name, "Request")
        resp_schema_name = _schema_name(tool_name, "Response")

        components_schemas[req_schema_name] = input_schema
        components_schemas[resp_schema_name] = output_schema

        route = f"/tools/{tool_name}"
        paths[route] = {
            "post": {
                "operationId": _safe_operation_id(tool_name),
                "summary": summary or tool_name,
                "description": (tool_desc or "").strip(),
                "tags": ["mcp-tools"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{req_schema_name}"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": _pick_output_description(tool),
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{resp_schema_name}"}
                            }
                        },
                    }
                },
            }
        }

    # 2) Deduplicate / extract common schemas across all components
    components_schemas = _dedupe_common_schemas_into_components(
        components_schemas,
        min_occurrences=2,   # only extract if it appears at least twice
    )

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": cfg.title,
            "version": cfg.version,
            "description": (
                "OpenAPI export of MCP tools metadata. "
                "Contains only operation descriptions and input/output schemas to support code generation. "
                "Schemas are defined in components.schemas; common sub-schemas are extracted once and reused via $ref."
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
# Common schema extraction / deduplication
# ============================================================

_META_KEYS = {
    "description", "title", "examples", "example", "default",
    # keep adding if you want local-only overrides:
    "deprecated",
}


def _dedupe_common_schemas_into_components(
    components_schemas: dict[str, Any],
    *,
    min_occurrences: int = 2,
) -> dict[str, Any]:
    """
    2-pass dedup:
      1) Count repeated "core schemas" across all components (including nested subschemas)
      2) Extract those cores as shared components and replace occurrences with $ref (or allOf wrapper)
    """
    # 1) Collect counts + store canonical representative cores
    counts: dict[str, int] = {}
    core_by_hash: dict[str, dict[str, Any]] = {}
    title_by_hash: dict[str, str] = {}

    def count_walk(schema: Any) -> None:
        for sub in _iter_subschemas(schema):
            if not isinstance(sub, dict):
                continue
            if "$ref" in sub:
                continue
            if sub == {}:
                continue

            core, meta = _split_core_and_meta(sub)
            h = _schema_core_hash(core)
            counts[h] = counts.get(h, 0) + 1

            # Keep a representative core + best title
            if h not in core_by_hash:
                core_by_hash[h] = core
            # Prefer explicit title, else maybe derive later
            t = meta.get("title")
            if isinstance(t, str) and t.strip():
                title_by_hash.setdefault(h, t.strip())

    for _, schema in components_schemas.items():
        count_walk(schema)

    # 2) Decide which hashes to extract
    extract_hashes = {h for h, c in counts.items() if c >= min_occurrences}

    # Assign stable component names
    used_names = set(components_schemas.keys())
    ref_name_by_hash: dict[str, str] = {}

    for h in sorted(extract_hashes):
        suggested = title_by_hash.get(h) or f"Schema_{h[:8]}"
        name = _unique_component_name(_sanitize_component_name(suggested), used_names)
        used_names.add(name)
        ref_name_by_hash[h] = name

    # Build extracted shared components first
    extracted_components: dict[str, Any] = {}
    for h, name in ref_name_by_hash.items():
        extracted_components[name] = core_by_hash[h]

    # Rewrite all component schemas to use refs
    def rewrite(schema: Any) -> Any:
        if isinstance(schema, list):
            return [rewrite(x) for x in schema]
        if not isinstance(schema, dict):
            return schema

        if "$ref" in schema:
            return schema

        # Recurse into children first
        out = {}
        for k, v in schema.items():
            if k in ("properties", "$defs"):
                if isinstance(v, dict):
                    out[k] = {pk: rewrite(pv) for pk, pv in v.items()}
                else:
                    out[k] = v
            elif k in ("items", "additionalProperties", "not"):
                out[k] = rewrite(v)
            elif k in ("allOf", "anyOf", "oneOf", "prefixItems"):
                out[k] = rewrite(v)
            else:
                out[k] = rewrite(v)

        # Now consider replacing THIS schema node with a ref
        if out == {}:
            return out

        core, meta = _split_core_and_meta(out)
        h = _schema_core_hash(core)
        if h not in ref_name_by_hash:
            return out

        ref = {"$ref": f"#/components/schemas/{ref_name_by_hash[h]}"}

        # If there is local metadata, keep it via allOf wrapper
        if meta:
            wrapper = {"allOf": [ref]}
            wrapper.update(meta)
            return wrapper

        return ref

    rewritten_components = {name: rewrite(schema) for name, schema in components_schemas.items()}

    # Merge extracted shared types + rewritten originals
    # (If a rewritten schema becomes a pure $ref, that's okay and valid.)
    merged: dict[str, Any] = {}
    merged.update(extracted_components)
    merged.update(rewritten_components)

    return merged


def _iter_subschemas(schema: Any) -> list[Any]:
    """
    Return a flat list of sub-schemas including the schema itself.
    Used for counting. (Recursive but iterative enough for typical schemas.)
    """
    out: list[Any] = []

    def rec(node: Any) -> None:
        out.append(node)

        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("properties", "$defs"):
                    if isinstance(v, dict):
                        for vv in v.values():
                            rec(vv)
                elif k in ("items", "additionalProperties", "not"):
                    rec(v)
                elif k in ("allOf", "anyOf", "oneOf", "prefixItems"):
                    if isinstance(v, list):
                        for vv in v:
                            rec(vv)
                # ignore other keys

        elif isinstance(node, list):
            for x in node:
                rec(x)

    rec(schema)
    return out


def _split_core_and_meta(schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Split a schema into:
      - core: structural schema used for dedup (no description/title/examples/default)
      - meta: those removed keys, so we can preserve them locally via allOf wrapper if needed
    """
    core: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    for k, v in schema.items():
        if k in _META_KEYS:
            # keep only meaningful meta
            if v is not None and v != "":
                meta[k] = v
        else:
            core[k] = v

    return core, meta


def _schema_core_hash(core: dict[str, Any]) -> str:
    """
    Stable hash for a schema core by canonical JSON.
    """
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _sanitize_component_name(name: str) -> str:
    # JSON Pointer friendly and codegen-friendly
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "Schema"


def _unique_component_name(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    i = 2
    while f"{base}_{i}" in used:
        i += 1
    return f"{base}_{i}"


# ============================================================
# Components schema naming
# ============================================================

def _schema_name(tool_name: str, suffix: str) -> str:
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
    cfg2 = ExportConfig(
        mcp_url="http://127.0.0.1:8080/mcp",
        bearer_token="",
        mcp_session_id="",
        title="My MCP Tools (Direct)",
        version="1.0.0",
    )

    out_file2 = export_mcp_tools_as_openapi_json_file(cfg2, "./out/mcp_tools_openapi_direct.json")
    print(f"Wrote OpenAPI JSON to: {out_file2}")
