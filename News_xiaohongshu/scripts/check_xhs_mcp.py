from __future__ import annotations

import json
import os
from itertools import count

import httpx


def main() -> None:
    base_url = os.getenv("XHS_MCP_BASE_URL", "http://127.0.0.1:18060").rstrip("/")
    mcp_url = base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"
    request_id = count(1)
    protocol = "2025-03-26"

    def rpc(client: httpx.Client, method: str, params: dict, session_id: str = "") -> tuple[dict, str]:
        payload = {"jsonrpc": "2.0", "id": next(request_id), "method": method, "params": params}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": protocol,
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        response = client.post(mcp_url, headers=headers, json=payload)
        response.raise_for_status()
        sid = response.headers.get("Mcp-Session-Id") or response.headers.get("MCP-Session-Id") or session_id
        return response.json(), sid

    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            init_data, sid = rpc(
                client,
                "initialize",
                {
                    "protocolVersion": protocol,
                    "clientInfo": {"name": "news_xiaohongshu_check", "version": "1.0.0"},
                    "capabilities": {},
                },
            )
            tools_data, sid = rpc(client, "tools/list", {}, sid)
            login_data, _ = rpc(client, "tools/call", {"name": "check_login_status", "arguments": {}}, sid)

        tools = tools_data.get("result", {}).get("tools", [])
        print(f"mcp_url={mcp_url}")
        print(f"session_id={sid}")
        print(f"initialize_ok={'error' not in init_data}")
        print(f"tools_count={len(tools) if isinstance(tools, list) else 0}")
        print("login_result=" + json.dumps(login_data.get("result", {}), ensure_ascii=True))
    except Exception as exc:
        print(f"check failed: {exc}")


if __name__ == "__main__":
    main()
