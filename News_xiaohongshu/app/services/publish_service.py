from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from sqlalchemy.orm import Session

from app.models.entities import Draft, PublishTask
from app.services.xhs_mcp_client import XhsMcpClient
from app.utils.text_sanitize import sanitize_tag


class PublishService:
    TITLE_MAX_LEN = 20
    CONTENT_MAX_LEN = 900

    def __init__(self, db: Session) -> None:
        self.db = db
        self.client = XhsMcpClient()

    def publish_draft(self, draft_id: int) -> PublishTask:
        draft = self.db.get(Draft, draft_id)
        if not draft:
            raise ValueError(f"Draft not found: {draft_id}")
        if draft.status != "approved":
            raise ValueError("Draft must be approved before publishing.")
        self._assert_xhs_session_logged_in()

        images = self._prepare_images(draft.cover_image_url)
        if not images:
            raise ValueError(
                "Publish requires at least one valid image. "
                "Please set Draft cover image to a direct image URL (.jpg/.png/.webp) or local file path."
            )

        publish_title = self._normalize_title(draft.title)
        if publish_title != draft.title:
            draft.title = publish_title

        tags = self._load_tags(draft.tags_json)
        publish_content = self._normalize_content(draft.content)
        payload = {"title": publish_title, "content": publish_content, "tags": tags}
        task = PublishTask(
            draft_id=draft.id,
            status="pending",
            request_payload=json.dumps(payload, ensure_ascii=False),
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        try:
            response = self.client.publish_article(
                title=publish_title,
                content=publish_content,
                tags=tags,
                images=images,
            )
            task.status = "succeeded"
            task.response_payload = json.dumps(response, ensure_ascii=False)
            draft.status = "published"
            draft.content = publish_content
            task.error_message = ""
        except Exception as exc:
            friendly = self._friendly_publish_error(str(exc))
            task.status = "failed"
            task.error_message = friendly
            task.response_payload = json.dumps({"error": friendly, "raw_error": str(exc)}, ensure_ascii=False)
            draft.status = "failed"

        self.db.commit()
        self.db.refresh(task)
        return task

    def _assert_xhs_session_logged_in(self) -> None:
        info = self.client.get_login_status()
        status = str(info.get("status", "")).strip().lower()
        raw = info.get("raw")
        is_logged_in = status == "logged_in"
        if isinstance(raw, dict) and isinstance(raw.get("is_logged_in"), bool):
            is_logged_in = bool(raw.get("is_logged_in"))
        if not is_logged_in:
            raise ValueError(
                "XHS automation session is not logged in. "
                "Please login in Admin page first, then retry publish."
            )

    def get_latest_task_for_draft(self, draft_id: int) -> PublishTask | None:
        from sqlalchemy import desc, select

        stmt = (
            select(PublishTask)
            .where(PublishTask.draft_id == draft_id)
            .order_by(desc(PublishTask.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    @staticmethod
    def _load_tags(raw: str) -> list[str]:
        try:
            loaded = json.loads(raw or "[]")
            if isinstance(loaded, list):
                clean: list[str] = []
                seen: set[str] = set()
                for tag in loaded:
                    item = sanitize_tag(str(tag))
                    if not item or item in seen:
                        continue
                    seen.add(item)
                    clean.append(item)
                return clean[:10]
        except Exception:
            pass
        return []

    @staticmethod
    def _split_image_candidates(raw: str) -> list[str]:
        if not raw:
            return []
        parts = re.split(r"[\n,;]+", raw)
        return [p.strip() for p in parts if p and p.strip()]

    def _prepare_images(self, raw_cover: str) -> list[str]:
        valid: list[str] = []
        for candidate in self._split_image_candidates(raw_cover):
            if self._is_valid_local_image(candidate):
                valid.append(candidate)
                continue
            if self._is_valid_remote_image(candidate):
                valid.append(candidate)
                continue
            fallback = self._fallback_remote_image(candidate)
            if fallback and self._is_valid_remote_image(fallback):
                valid.append(fallback)
        return valid

    @staticmethod
    def _fallback_remote_image(value: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        parsed = urlparse(v)
        host = (parsed.netloc or "").lower()
        if "source.unsplash.com" in host:
            seed = hashlib.sha1(v.encode("utf-8")).hexdigest()[:16]
            return f"https://picsum.photos/seed/{seed}/1200/1600.jpg"
        return ""

    @staticmethod
    def _is_valid_local_image(value: str) -> bool:
        v = (value or "").strip()
        if not v:
            return False
        if v.startswith(("http://", "https://")):
            return False
        p = Path(v).expanduser()
        if not p.exists() or not p.is_file():
            return False
        return p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    @staticmethod
    def _is_valid_remote_image(value: str) -> bool:
        v = (value or "").strip()
        if not v:
            return False
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.netloc or "").lower()
        if host.endswith("image.thum.io"):
            return True

        path = (parsed.path or "").lower()
        if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            return True

        # If no image extension is present, do a lightweight content-type probe.
        try:
            with httpx.Client(timeout=8, follow_redirects=True, trust_env=False) as client:
                head_resp = client.head(v)
                ctype = (head_resp.headers.get("content-type") or "").lower()
                if head_resp.is_success and ctype.startswith("image/"):
                    return True
                if head_resp.status_code in (405, 403) or not head_resp.is_success:
                    get_resp = client.get(v, headers={"Range": "bytes=0-0"})
                    ctype = (get_resp.headers.get("content-type") or "").lower()
                    if get_resp.is_success and ctype.startswith("image/"):
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _normalize_title(title: str) -> str:
        text = (title or "").strip()
        if len(text) <= PublishService.TITLE_MAX_LEN:
            return text
        return text[: PublishService.TITLE_MAX_LEN]

    @staticmethod
    def _normalize_content(content: str) -> str:
        text = (content or "").strip()
        if len(text) <= PublishService.CONTENT_MAX_LEN:
            return text
        clipped = text[: PublishService.CONTENT_MAX_LEN]
        if "\n" in clipped:
            clipped = clipped.rsplit("\n", 1)[0].rstrip()
        suffix = "\n\n（内容已自动精简以满足平台发布限制）"
        if len(clipped) + len(suffix) > PublishService.CONTENT_MAX_LEN:
            clipped = clipped[: PublishService.CONTENT_MAX_LEN - len(suffix)].rstrip()
        return clipped + suffix

    @staticmethod
    def _friendly_publish_error(raw: str) -> str:
        msg = (raw or "").strip()
        lowered = msg.lower()
        m = re.search(r"debug_screenshot=([^\s\"}]+)", msg)
        debug_path = m.group(1) if m else ""
        debug_hint = f" Debug screenshot: {debug_path}" if debug_path else ""

        if "publish submitted but not confirmed" in lowered:
            return (
                "Publish failed: click was sent but platform did not confirm success/review state. "
                "Keep creator page in foreground and retry." + debug_hint
            )
        if "publish validation failed" in lowered:
            return "Publish failed: platform validation rejected the content (title/content/images or page rule). " + debug_hint
        if "publish blocked by risk control" in lowered:
            return "Publish failed: platform risk control/challenge detected. Please complete verification in browser and retry." + debug_hint
        if "publish blocked by ui hint" in lowered and ("禁止发笔记" in msg or "社区规范" in msg):
            return "Publish failed: your account is restricted by platform policy (forbidden to publish). Please check Xiaohongshu creator-center violations/appeal first." + debug_hint
        if "http 461" in lowered or "website-login/error" in lowered:
            return "Publish failed: platform blocked this environment (IP/device risk). Try a stable network and normal login environment."
        if "not logged in" in lowered or "creator center not logged in" in lowered:
            return "Publish failed: creator center session is not logged in. Re-login and retry."
        if "publish editor not ready" in lowered:
            return "Publish failed: publish editor is not ready. Open creator publish page in foreground and retry." + debug_hint
        if "publish tab not found" in lowered:
            return "Publish failed: publish page structure changed and image tab was not found." + debug_hint
        if "title input not found" in lowered or "content input not found" in lowered:
            return "Publish failed: title/content editor was not found on publish page." + debug_hint
        if "upload input not found" in lowered:
            return "Publish failed: image upload input was not found on publish page." + debug_hint
        if "unexpected publish url" in lowered:
            return "Publish failed: current browser page is not the creator publish page."
        if "image upload timeout" in lowered:
            return "Publish failed: image upload timeout. Try smaller image or retry."
        if "execution context was destroyed" in lowered or "intercepts pointer events" in lowered:
            return "Publish failed: page navigation/loading interrupted click. Keep browser foreground and retry."
        if "timed out" in lowered:
            return "Publish failed: MCP call timed out. Retry later or increase timeout setting."
        if "503 service unavailable" in lowered or "source.unsplash.com" in lowered:
            return "Publish failed: remote cover image source unavailable. Use local image file and retry."

        return f"Publish failed: {msg}"
