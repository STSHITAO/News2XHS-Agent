from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_initialize_returns_session_and_protocol() -> None:
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("Mcp-Session-Id")
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["result"]["serverInfo"]["name"] == "xiaohongshu-mcp"


def test_tools_list_requires_valid_session_when_header_provided() -> None:
    client = TestClient(app)
    resp = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": "invalid-session"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"]["code"] == -32001


def test_tools_list_success_after_initialize() -> None:
    client = TestClient(app)
    init_resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}},
    )
    sid = init_resp.headers.get("Mcp-Session-Id")
    assert sid

    resp = client.post(
        "/mcp",
        headers={"Mcp-Session-Id": sid},
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    tools = body["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 13
