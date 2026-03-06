from __future__ import annotations

import json
from typing import Any

from app.browser_automation import XhsAutomation, XhsError
from app.mcp_types import tool_text_result


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


TOOLS: list[dict[str, Any]] = [
    {
        "name": "check_login_status",
        "description": "检查小红书登录状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_login_qrcode",
        "description": "获取登录二维码（返回 Base64 图片和超时信息）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_cookies",
        "description": "删除 cookies 并重置登录状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "publish_content",
        "description": "发布图文内容到小红书",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "images": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "schedule_at": {"type": "string"},
            },
            "required": ["title", "content", "images"],
        },
    },
    {
        "name": "publish_with_video",
        "description": "发布视频内容到小红书（本地单视频文件）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "video": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "schedule_at": {"type": "string"},
            },
            "required": ["title", "content", "video"],
        },
    },
    {
        "name": "list_feeds",
        "description": "获取首页推荐列表",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_feeds",
        "description": "按关键词搜索小红书内容，可选筛选条件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "filters": {
                    "type": "object",
                    "properties": {
                        "sort_by": {"type": "string"},
                        "note_type": {"type": "string"},
                        "publish_time": {"type": "string"},
                        "search_scope": {"type": "string"},
                        "location": {"type": "string"},
                    },
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_feed_detail",
        "description": "获取笔记详情与评论数据",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed_id": {"type": "string"},
                "xsec_token": {"type": "string"},
                "load_all_comments": {"type": "boolean"},
                "limit": {"type": "integer"},
                "click_more_replies": {"type": "boolean"},
                "reply_limit": {"type": "integer"},
                "scroll_speed": {"type": "string"},
            },
            "required": ["feed_id", "xsec_token"],
        },
    },
    {
        "name": "user_profile",
        "description": "获取用户主页资料和笔记",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "xsec_token": {"type": "string"},
            },
            "required": ["user_id", "xsec_token"],
        },
    },
    {
        "name": "post_comment_to_feed",
        "description": "在笔记下发表评论",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed_id": {"type": "string"},
                "xsec_token": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["feed_id", "xsec_token", "content"],
        },
    },
    {
        "name": "reply_comment_in_feed",
        "description": "回复笔记下的指定评论",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed_id": {"type": "string"},
                "xsec_token": {"type": "string"},
                "comment_id": {"type": "string"},
                "user_id": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["feed_id", "xsec_token", "content"],
        },
    },
    {
        "name": "like_feed",
        "description": "点赞或取消点赞",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed_id": {"type": "string"},
                "xsec_token": {"type": "string"},
                "unlike": {"type": "boolean"},
            },
            "required": ["feed_id", "xsec_token"],
        },
    },
    {
        "name": "favorite_feed",
        "description": "收藏或取消收藏",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed_id": {"type": "string"},
                "xsec_token": {"type": "string"},
                "unfavorite": {"type": "boolean"},
            },
            "required": ["feed_id", "xsec_token"],
        },
    },
]


class ToolExecutor:
    def __init__(self) -> None:
        self.xhs = XhsAutomation()

    def list_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "check_login_status":
                data = self.xhs.check_login_status()
                text = (
                    f"✅ 已登录\n用户名: {data.get('username', '')}" if data["is_logged_in"] else "❌ 未登录\n请调用 get_login_qrcode 获取二维码"
                )
                return {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "get_login_qrcode":
                data = self.xhs.get_login_qrcode()
                if data.get("is_logged_in"):
                    return {
                        "content": [{"type": "text", "text": "你当前已经处于登录状态"}],
                        "isError": False,
                        "structuredContent": data,
                    }
                return {
                    "content": [
                        {"type": "text", "text": "请使用小红书 App 扫码登录"},
                        {"type": "image", "mimeType": "image/png", "data": data.get("img", "")},
                    ],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "delete_cookies":
                data = self.xhs.delete_cookies()
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "publish_content":
                data = self.xhs.publish_content(
                    title=str(arguments.get("title", "")),
                    content=str(arguments.get("content", "")),
                    images=[str(x) for x in (arguments.get("images") or [])],
                    tags=[str(x) for x in (arguments.get("tags") or [])],
                    schedule_at=str(arguments.get("schedule_at") or ""),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "publish_with_video":
                data = self.xhs.publish_with_video(
                    title=str(arguments.get("title", "")),
                    content=str(arguments.get("content", "")),
                    video=str(arguments.get("video", "")),
                    tags=[str(x) for x in (arguments.get("tags") or [])],
                    schedule_at=str(arguments.get("schedule_at") or ""),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "list_feeds":
                data = self.xhs.list_feeds()
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "search_feeds":
                data = self.xhs.search_feeds(
                    keyword=str(arguments.get("keyword", "")),
                    filters=arguments.get("filters") or {},
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "get_feed_detail":
                load_all_comments = bool(arguments.get("load_all_comments") or False)
                limit = arguments.get("limit")
                reply_limit = arguments.get("reply_limit")
                max_comment_items = int(limit) if limit not in (None, "") else (20 if load_all_comments else 0)
                max_replies_threshold = int(reply_limit) if reply_limit not in (None, "") else 10
                config = {
                    "max_comment_items": max_comment_items,
                    "click_more_replies": bool(arguments.get("click_more_replies") or False),
                    "max_replies_threshold": max_replies_threshold,
                    "scroll_speed": str(arguments.get("scroll_speed") or "normal"),
                }
                data = self.xhs.get_feed_detail(
                    feed_id=str(arguments.get("feed_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                    load_all_comments=load_all_comments,
                    config=config,
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "user_profile":
                data = self.xhs.user_profile(
                    user_id=str(arguments.get("user_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "post_comment_to_feed":
                data = self.xhs.post_comment(
                    feed_id=str(arguments.get("feed_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                    content=str(arguments.get("content", "")),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "reply_comment_in_feed":
                data = self.xhs.reply_comment(
                    feed_id=str(arguments.get("feed_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                    content=str(arguments.get("content", "")),
                    comment_id=str(arguments.get("comment_id", "")),
                    user_id=str(arguments.get("user_id", "")),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "like_feed":
                data = self.xhs.like_feed(
                    feed_id=str(arguments.get("feed_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                    unlike=bool(arguments.get("unlike") or False),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            if name == "favorite_feed":
                data = self.xhs.favorite_feed(
                    feed_id=str(arguments.get("feed_id", "")),
                    xsec_token=str(arguments.get("xsec_token", "")),
                    unfavorite=bool(arguments.get("unfavorite") or False),
                )
                return {
                    "content": [{"type": "text", "text": _json_text(data)}],
                    "isError": False,
                    "structuredContent": data,
                }

            return tool_text_result(f"unknown tool: {name}", is_error=True)

        except XhsError as exc:
            return tool_text_result(str(exc), is_error=True)
        except Exception as exc:
            return tool_text_result(f"internal error: {exc}", is_error=True)
