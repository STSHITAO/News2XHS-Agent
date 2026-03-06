from __future__ import annotations

from typing import Any


def ok_result(payload: dict[str, Any], request_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def err_result(code: int, message: str, request_id: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def tool_text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def tool_image_result(base64_data: str, mime_type: str = "image/png") -> dict[str, Any]:
    return {
        "content": [{"type": "image", "data": base64_data, "mimeType": mime_type}],
        "isError": False,
    }
