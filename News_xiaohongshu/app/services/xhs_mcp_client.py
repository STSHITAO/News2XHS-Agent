from __future__ import annotations

import json
import time
from itertools import count
from typing import Any

import httpx

from app.core.config import settings


class XhsMcpClient:
    def __init__(self) -> None:
        self.base_url = settings.XHS_MCP_BASE_URL.rstrip("/")
        self.mcp_url = self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"
        # Browser automation may take longer than generic API calls.
        self.timeout = max(120, int(settings.XHS_PUBLISH_TIMEOUT))
        self.api_key = settings.XHS_MCP_API_KEY.strip()
        self._request_id = count(1)
        self._tools_cache: list[dict[str, Any]] | None = None
        self._session_id: str = ""
        self._protocol_version: str = "2025-03-26"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self._protocol_version,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _json_rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": next(self._request_id),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            response = client.post(self.mcp_url, headers=self._headers(), json=payload)
            response.raise_for_status()
            session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("MCP-Session-Id")
            if session_id:
                self._session_id = session_id.strip()
            data = response.json()

        if "error" in data:
            raise RuntimeError(f"MCP error on {method}: {data['error']}")
        result = data.get("result")
        if not isinstance(result, dict):
            return {}
        return result

    def _initialize(self) -> None:
        init_params = {
            "protocolVersion": "2025-03-26",
            "clientInfo": {"name": "news_xiaohongshu", "version": "0.2.0"},
            "capabilities": {},
        }
        try:
            result = self._json_rpc("initialize", init_params)
        except Exception:
            # Some servers accept empty initialize params only.
            result = self._json_rpc("initialize", {})
        protocol_version = result.get("protocolVersion")
        if isinstance(protocol_version, str) and protocol_version.strip():
            self._protocol_version = protocol_version.strip()

    def _list_tools(self) -> list[dict[str, Any]]:
        if self._tools_cache is not None:
            return self._tools_cache

        self._initialize()
        result = self._json_rpc("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            tools = []
        self._tools_cache = [tool for tool in tools if isinstance(tool, dict)]
        return self._tools_cache

    @staticmethod
    def _extract_payload(call_result: dict[str, Any]) -> dict[str, Any]:
        if isinstance(call_result.get("structuredContent"), dict):
            return call_result["structuredContent"]

        content = call_result.get("content")
        if isinstance(content, list):
            text_chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if not isinstance(text, str):
                    continue
                raw = text.strip()
                if not raw:
                    continue
                text_chunks.append(raw)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
                return {"data": parsed}
            if text_chunks:
                return {"text": "\n".join(text_chunks)}

        return call_result if isinstance(call_result, dict) else {"raw": call_result}

    @staticmethod
    def _extract_image_data(call_result: dict[str, Any]) -> str:
        content = call_result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type", "")).lower() != "image":
                    continue
                data = item.get("data")
                if isinstance(data, str) and data.strip():
                    return data.strip()
        return ""

    @staticmethod
    def _extract_error(call_result: dict[str, Any]) -> str:
        payload = XhsMcpClient._extract_payload(call_result)
        if isinstance(payload, dict):
            for key in ("error", "message", "msg", "detail"):
                value = payload.get(key)
                if value:
                    return str(value)
        return json.dumps(payload, ensure_ascii=False)

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._json_rpc("tools/call", {"name": tool_name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"Tool '{tool_name}' returned error: {self._extract_error(result)}")
        return result

    @staticmethod
    def _brief_args(arguments: dict[str, Any]) -> dict[str, Any]:
        brief = dict(arguments)
        if "content" in brief:
            content = str(brief.get("content", ""))
            brief["content"] = f"<len={len(content)}>"
        if "description" in brief:
            desc = str(brief.get("description", ""))
            brief["description"] = f"<len={len(desc)}>"
        return brief

    def _find_tool(self, candidates: list[str], fuzzy_keywords: list[str]) -> dict[str, Any]:
        tools = self._list_tools()
        by_name = {str(tool.get("name", "")): tool for tool in tools}

        for name in candidates:
            tool = by_name.get(name)
            if tool:
                return tool

        for tool in tools:
            name = str(tool.get("name", "")).lower()
            if name and all(keyword in name for keyword in fuzzy_keywords):
                return tool

        available = [str(tool.get("name", "")) for tool in tools]
        raise RuntimeError(f"No compatible MCP tool found. available={available}")

    @staticmethod
    def _build_publish_args_from_schema(
        tool: dict[str, Any],
        *,
        title: str,
        content: str,
        tags: list[str],
        images: list[str],
    ) -> dict[str, Any]:
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict) or not properties:
            return {}

        args: dict[str, Any] = {}

        def set_if_exists(aliases: list[str], value: Any) -> None:
            for key in aliases:
                if key in properties and key not in args:
                    args[key] = value
                    return

        set_if_exists(["title", "note_title"], title)
        set_if_exists(["content", "description", "desc", "body", "text"], content)
        set_if_exists(["tags", "topics", "topic_tags", "hashtags"], tags)
        set_if_exists(
            ["images", "image_urls", "image_paths", "media_paths", "media", "photos"],
            images,
        )

        if "type" in properties and "type" not in args:
            args["type"] = "image"
        if "publish_type" in properties and "publish_type" not in args:
            args["publish_type"] = "image"

        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        canonical_defaults: dict[str, Any] = {
            "title": title,
            "note_title": title,
            "content": content,
            "description": content,
            "desc": content,
            "body": content,
            "text": content,
            "tags": tags,
            "topics": tags,
            "topic_tags": tags,
            "hashtags": tags,
            "images": images,
            "image_urls": images,
            "image_paths": images,
            "media_paths": images,
            "media": images,
            "photos": images,
            "type": "image",
            "publish_type": "image",
        }
        for key in required:
            if key in args:
                continue
            if key in canonical_defaults:
                args[key] = canonical_defaults[key]

        return args

    def get_login_status(self) -> dict[str, Any]:
        tool = self._find_tool(
            candidates=["check_login_status", "xhs_auth_status", "auth_status", "login_status"],
            fuzzy_keywords=["login", "status"],
        )
        tool_name = str(tool.get("name", "check_login_status"))
        result = self._call_tool(tool_name, {})
        payload = self._extract_payload(result)

        status = "unknown"
        if isinstance(payload, dict):
            for key in ("status", "login_status", "state"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    status = value.strip()
                    break
            else:
                logged = payload.get("is_logged_in")
                if isinstance(logged, bool):
                    status = "logged_in" if logged else "logged_out"

        return {"success": True, "status": status, "tool": tool_name, "raw": payload}

    def get_login_qrcode(self) -> dict[str, Any]:
        tool = self._find_tool(
            candidates=["get_login_qrcode", "xhs_login_qrcode", "login_qrcode"],
            fuzzy_keywords=["login", "qrcode"],
        )
        tool_name = str(tool.get("name", "get_login_qrcode"))
        result = self._call_tool(tool_name, {})
        payload = self._extract_payload(result)

        is_logged_in = False
        timeout = ""
        image_data = ""
        if isinstance(payload, dict):
            is_logged_in = bool(payload.get("is_logged_in"))
            timeout = str(payload.get("timeout") or "")
            image_data = str(payload.get("img") or "").strip()
        if not image_data:
            image_data = self._extract_image_data(result)

        status = "logged_in" if is_logged_in else "not_logged_in"
        return {
            "success": True,
            "status": status,
            "tool": tool_name,
            "timeout": timeout,
            "img": image_data,
            "raw": payload,
        }

    def reset_login(self) -> dict[str, Any]:
        tool = self._find_tool(
            candidates=["delete_cookies", "xhs_delete_cookies", "reset_login"],
            fuzzy_keywords=["cookies"],
        )
        tool_name = str(tool.get("name", "delete_cookies"))
        result = self._call_tool(tool_name, {})
        payload = self._extract_payload(result)
        return {"success": True, "tool": tool_name, "raw": payload}

    def publish_article(
        self,
        *,
        title: str,
        content: str,
        tags: list[str],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        images = images or []
        tags = [str(tag) for tag in tags]

        tool = self._find_tool(
            candidates=["publish_content", "xhs_publish_content", "publish_note", "xhs_publish_note"],
            fuzzy_keywords=["publish"],
        )
        tool_name = str(tool.get("name", "publish_content"))

        candidates: list[dict[str, Any]] = []
        schema_args = self._build_publish_args_from_schema(
            tool,
            title=title,
            content=content,
            tags=tags,
            images=images,
        )
        if schema_args:
            candidates.append(schema_args)

        candidates.extend(
            [
                {"title": title, "content": content, "tags": tags, "images": images},
                {
                    "type": "image",
                    "title": title,
                    "content": content,
                    "media_paths": images,
                    "tags": tags,
                },
                {
                    "title": title,
                    "description": content,
                    "image_urls": images,
                    "topics": tags,
                },
            ]
        )

        # Local python MCP uses publish_content(title/content/images) as canonical schema.
        if tool_name == "publish_content":
            canonical: list[dict[str, Any]] = []
            for item in candidates:
                has_required = (
                    isinstance(item, dict)
                    and isinstance(item.get("title"), str)
                    and isinstance(item.get("content"), str)
                    and isinstance(item.get("images"), list)
                )
                if has_required:
                    canonical.append(item)
            if canonical:
                candidates = canonical

        tried_signatures: set[str] = set()
        errors: list[str] = []
        for idx, args in enumerate(candidates, start=1):
            signature = json.dumps(args, ensure_ascii=False, sort_keys=True)
            if signature in tried_signatures:
                continue
            tried_signatures.add(signature)

            max_try = 3
            for i in range(max_try):
                try:
                    result = self._call_tool(tool_name, args)
                    payload = self._extract_payload(result)
                    return {"success": True, "tool": tool_name, "request": args, "raw": payload}
                except Exception as exc:
                    text = str(exc).lower()
                    transient = any(
                        k in text
                        for k in (
                            "timed out",
                            "execution context was destroyed",
                            "intercepts pointer events",
                            "connection reset",
                            "connection aborted",
                            "target closed",
                            "page crashed",
                            "navigation",
                            "publish editor not ready",
                            "title input not found",
                            "content input not found",
                            "upload input not found",
                            "publish button click failed",
                        )
                    )
                    if transient and i < max_try - 1:
                        time.sleep(2.0 * (i + 1))
                        continue
                    errors.append(f"attempt#{idx}.{i+1} args={self._brief_args(args)} err={exc}")
                    break

        raise RuntimeError(f"MCP publish failed after {len(errors)} attempts. " + " | ".join(errors))
