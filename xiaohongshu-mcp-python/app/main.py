from __future__ import annotations

import logging
import secrets
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.mcp_types import err_result, ok_result
from app.tools import ToolExecutor


logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("xiaohongshu_mcp_python")

app = FastAPI(title="xiaohongshu-mcp-python", version="1.0.0")
executor = ToolExecutor()
sessions: dict[str, str] = {}


def _new_session_id() -> str:
    return secrets.token_urlsafe(24)


def _runtime_port(default_port: int = 18060) -> int:
    for idx, token in enumerate(sys.argv):
        if token == "--port" and idx + 1 < len(sys.argv):
            try:
                return int(sys.argv[idx + 1])
            except Exception:
                return default_port
        if token.startswith("--port="):
            try:
                return int(token.split("=", 1)[1])
            except Exception:
                return default_port
    return default_port


def _response(payload: dict[str, Any], session_id: str | None = None) -> JSONResponse:
    res = JSONResponse(payload)
    if session_id:
        res.headers["Mcp-Session-Id"] = session_id
    res.headers["MCP-Protocol-Version"] = settings.MCP_PROTOCOL_VERSION
    return res


@app.on_event("startup")
def log_startup_urls() -> None:
    port = _runtime_port()
    logger.info("xiaohongshu-mcp-python started.")
    logger.info("Health: http://127.0.0.1:%s/health", port)
    logger.info("MCP endpoint: http://127.0.0.1:%s/mcp", port)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"success": True, "service": "xiaohongshu-mcp-python"}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _response(err_result(-32700, "Parse error", None))

    if not isinstance(body, dict):
        return _response(err_result(-32600, "Invalid Request", None))

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if method == "initialize":
        session_id = _new_session_id()
        client_protocol = ""
        if isinstance(params, dict):
            client_protocol = str(params.get("protocolVersion") or "")
        sessions[session_id] = client_protocol or settings.MCP_PROTOCOL_VERSION
        payload = {
            "capabilities": {"tools": {"listChanged": True}, "logging": {}},
            "protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "serverInfo": {"name": "xiaohongshu-mcp", "version": "2.0.0"},
        }
        return _response(ok_result(payload, req_id), session_id=session_id)

    if method == "notifications/initialized":
        return _response(ok_result({}, req_id))

    if method == "tools/list":
        sid = request.headers.get("Mcp-Session-Id", "")
        if sid and sid not in sessions:
            return _response(err_result(-32001, "Invalid MCP session", req_id))
        payload = {"tools": executor.list_tools()}
        return _response(ok_result(payload, req_id), session_id=(sid or None))

    if method == "tools/call":
        sid = request.headers.get("Mcp-Session-Id", "")
        if sid and sid not in sessions:
            return _response(err_result(-32001, "Invalid MCP session", req_id))

        if not isinstance(params, dict):
            return _response(err_result(-32602, "Invalid params", req_id), session_id=(sid or None))

        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _response(err_result(-32602, "arguments must be an object", req_id), session_id=(sid or None))

        result = await run_in_threadpool(executor.call, name, arguments)
        return _response(ok_result(result, req_id), session_id=(sid or None))

    return _response(err_result(-32601, f"Method not found: {method}", req_id))
