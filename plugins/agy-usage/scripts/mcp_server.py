#!/usr/bin/env python3
"""Zero-dependency MCP 2024-11-05 stdio server (newline-delimited JSON-RPC, read-only & sanitized)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from instance_lock import APP_VERSION  # noqa: E402
from pure_query import (  # noqa: E402
    query_cache_health,
    query_health,
    query_quota_status,
    query_usage_summary,
)

SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26")
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agy-usage-quota", "version": APP_VERSION}
MAX_LINE_BYTES = 65536

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "agy_usage_summary",
        "description": "Get sanitized Antigravity token usage & estimated list-price cost summary for today, 7d, or 30d.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "enum": ["today", "7d", "30d"],
                    "description": "Aggregation window (default: 7d).",
                },
                "model": {
                    "type": "string",
                    "maxLength": 128,
                    "description": "Optional case-insensitive model substring filter.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agy_usage_quota",
        "description": "Get dual-pool four-bucket Antigravity quota remaining percentages and reset countdowns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "agy_usage_cache_health",
        "description": "Get prompt cache hit rate and estimated savings for today, 7d, or 30d.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window": {
                    "type": "string",
                    "enum": ["today", "7d", "30d"],
                    "description": "Aggregation window (default: 7d).",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agy_usage_health",
        "description": "Check read-only boolean status of statusline, live_state, transcripts, and local dashboard daemon.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def _err(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _ok(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _call_tool(name: str, arguments: Any) -> Dict[str, Any]:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")

    if name == "agy_usage_summary":
        extra = set(arguments.keys()) - {"window", "model"}
        if extra:
            raise ValueError(f"unexpected arguments: {sorted(extra)}")
        window = arguments.get("window", "7d")
        model = arguments.get("model")
        return query_usage_summary(window=window, model=model)

    if name == "agy_usage_quota":
        if arguments:
            raise ValueError(f"unexpected arguments: {sorted(arguments.keys())}")
        return query_quota_status()

    if name == "agy_usage_cache_health":
        extra = set(arguments.keys()) - {"window"}
        if extra:
            raise ValueError(f"unexpected arguments: {sorted(extra)}")
        return query_cache_health(window=arguments.get("window", "7d"))

    if name == "agy_usage_health":
        if arguments:
            raise ValueError(f"unexpected arguments: {sorted(arguments.keys())}")
        return query_health()

    raise KeyError(f"unknown tool: {name}")


def handle_message(msg: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _err(None, -32600, "Invalid JSON-RPC 2.0 request")

    has_id = "id" in msg
    req_id = msg.get("id")
    method = msg.get("method")
    if not isinstance(method, str) or not method:
        return _err(req_id, -32600, "Missing or invalid method") if has_id else None

    # Notifications have no id and MUST NOT produce a response
    if not has_id:
        return None

    params = msg.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _err(req_id, -32602, "params must be an object")

    if method == "initialize":
        client_ver = params.get("protocolVersion")
        negotiated = client_ver if client_ver in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        return _ok(
            req_id,
            {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "ping":
        return _ok(req_id, {})

    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tname = params.get("name")
        if not isinstance(tname, str) or not tname:
            return _err(req_id, -32602, "Missing tool name")
        try:
            data = _call_tool(tname, params.get("arguments"))
            text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            return _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except KeyError as exc:
            return _err(req_id, -32602, str(exc))
        except ValueError as exc:
            return _err(req_id, -32602, str(exc))
        except Exception as exc:
            sys.stderr.write(f"[agy-usage-mcp] tool error ({tname}): {exc}\n")
            sys.stderr.flush()
            err_text = json.dumps({"ok": False, "error": "internal query error"}, separators=(",", ":"))
            return _ok(req_id, {"content": [{"type": "text", "text": err_text}], "isError": True})

    return _err(req_id, -32601, f"Method not found: {method}")


def _write_frame(out: Any, payload: Dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    out.write(line + "\n")
    out.flush()


def serve_stdio(stdin: Any = None, stdout: Any = None) -> int:
    in_stream = stdin if stdin is not None else sys.stdin.buffer
    out_stream = stdout if stdout is not None else sys.stdout
    while True:
        raw = in_stream.readline(MAX_LINE_BYTES + 1)
        if not raw:
            break
        if isinstance(raw, str):
            raw_bytes = raw.encode("utf-8", errors="replace")
        else:
            raw_bytes = raw
        if len(raw_bytes) > MAX_LINE_BYTES:
            # Drain remainder of oversized line
            while not raw_bytes.endswith(b"\n"):
                chunk = in_stream.readline(MAX_LINE_BYTES)
                if not chunk:
                    break
                raw_bytes = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8", errors="replace")
            _write_frame(out_stream, _err(None, -32600, f"Request exceeds {MAX_LINE_BYTES} byte limit"))
            continue
        stripped = raw_bytes.strip()
        if not stripped:
            continue
        try:
            msg = json.loads(stripped.decode("utf-8"))
        except Exception:
            _write_frame(out_stream, _err(None, -32700, "Parse error"))
            continue
        resp = handle_message(msg)
        if resp is not None:
            _write_frame(out_stream, resp)
    return 0


def main() -> int:
    try:
        return serve_stdio()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        sys.stderr.write(f"[agy-usage-mcp] fatal: {exc}\n")
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    sys.exit(main())
