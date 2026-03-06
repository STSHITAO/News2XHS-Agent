from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Draft, NewsItem
from app.utils.text_sanitize import sanitize_tag, sanitize_topic


class DraftService:
    TITLE_MAX_LEN = 20
    IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_draft(self, topic: str, max_news_items: int = 5) -> Draft:
        clean_topic = sanitize_topic(topic, max_len=20)
        items = self._select_news_items(topic=clean_topic, limit=max_news_items)
        if not items:
            raise ValueError("No news items found. Run /api/news/hot/fetch first.")

        title = self._build_title(clean_topic)
        content = self._build_content(clean_topic, items)
        tags = self._build_tags(clean_topic)
        cover = self._extract_cover_image(items)

        draft = Draft(
            topic=clean_topic,
            title=title,
            content=content,
            tags_json=json.dumps(tags, ensure_ascii=False),
            cover_image_url=cover,
            status="pending_review",
            source_item_id=items[0].id if items else None,
        )
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def list_drafts(self, limit: int = 100, status: str | None = None) -> list[Draft]:
        stmt = select(Draft).order_by(desc(Draft.created_at)).limit(limit)
        if status:
            stmt = select(Draft).where(Draft.status == status).order_by(desc(Draft.created_at)).limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_draft(self, draft_id: int) -> Draft:
        return self._get_draft_or_raise(draft_id)

    def update_draft(
        self,
        draft_id: int,
        *,
        title: str,
        content: str,
        tags: list[str],
        cover_image_url: str,
        editor_notes: str = "",
    ) -> Draft:
        draft = self._get_draft_or_raise(draft_id)
        draft.title = self._normalize_title(title)
        draft.content = content.strip()
        draft.tags_json = json.dumps(self._normalize_tags(tags), ensure_ascii=False)
        draft.cover_image_url = (cover_image_url or "").strip()
        draft.editor_notes = editor_notes
        if draft.status in {"rejected", "failed"}:
            draft.status = "pending_review"
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def approve_draft(self, draft_id: int, notes: str = "") -> Draft:
        draft = self._get_draft_or_raise(draft_id)
        draft.status = "approved"
        draft.editor_notes = notes
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def reject_draft(self, draft_id: int, notes: str = "") -> Draft:
        draft = self._get_draft_or_raise(draft_id)
        draft.status = "rejected"
        draft.editor_notes = notes
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def _select_news_items(self, topic: str, limit: int) -> list[NewsItem]:
        keyword = f"%{topic}%"
        stmt = (
            select(NewsItem)
            .where(NewsItem.title.like(keyword))
            .order_by(desc(NewsItem.created_at))
            .limit(limit)
        )
        rows = list(self.db.scalars(stmt).all())
        if rows:
            return rows
        fallback_stmt = select(NewsItem).order_by(desc(NewsItem.created_at)).limit(limit)
        return list(self.db.scalars(fallback_stmt).all())

    @staticmethod
    def _build_title(topic: str) -> str:
        date_text = datetime.now().strftime("%m月%d日")
        return DraftService._normalize_title(f"{date_text} {topic}热点速览")

    @staticmethod
    def _normalize_title(title: str) -> str:
        text = (title or "").strip()
        if len(text) <= DraftService.TITLE_MAX_LEN:
            return text
        return text[: DraftService.TITLE_MAX_LEN]

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        clean: list[str] = []
        seen: set[str] = set()
        for raw in tags:
            item = sanitize_tag(str(raw))
            if not item or item in seen:
                continue
            seen.add(item)
            clean.append(item)
        return clean[:10]

    @staticmethod
    def _build_tags(topic: str) -> list[str]:
        base = ["热点新闻", "行业观察", "信息整理", "半自动发布"]
        clean_topic = sanitize_tag(topic)
        if clean_topic and clean_topic not in base:
            base.insert(0, clean_topic)
        return base[:6]

    @staticmethod
    def _build_content(topic: str, items: list[NewsItem]) -> str:
        lines = [
            f"【今日主题】{topic}",
            "",
            "先说结论：今天最值得关注的是以下几点。",
            "",
        ]
        for idx, item in enumerate(items[:5], start=1):
            lines.append(f"{idx}. {item.title}")
            lines.append(f"   - 核心信息：{(item.summary or '')[:120]}")
            lines.append(f"   - 参考链接：{item.url}")
        lines.extend(
            [
                "",
                "【我的观察】",
                "1) 热点传播速度继续加快，跨平台扩散明显。",
                "2) 观点分化增加，建议关注评论区的真实用户反馈。",
                "3) 后续可追踪政策、企业回应和二级市场反应。",
                "",
                "（本稿为半自动生成草稿，发布前请人工校对事实与措辞）",
            ]
        )
        return "\n".join(lines)

    def _extract_cover_image(self, items: list[NewsItem]) -> str:
        default_local = self._resolve_default_local_cover()
        if default_local:
            return default_local

        local_from_items = self._extract_local_cover_from_items(items)
        if local_from_items:
            return local_from_items

        if settings.LOCAL_COVER_ONLY:
            return ""

        for item in items:
            raw = {}
            try:
                raw = json.loads(item.raw_json or "{}")
                if not isinstance(raw, dict):
                    raw = {}
            except Exception:
                raw = {}
            for key in ("image", "image_url", "imageUrl", "cover", "cover_url", "thumbnail", "thumbnailUrl"):
                value = raw.get(key)
                if isinstance(value, str) and self._looks_like_remote_image_ref(value):
                    return value.strip()
        return ""

    def _extract_local_cover_from_items(self, items: list[NewsItem]) -> str:
        for item in items:
            raw = {}
            try:
                raw = json.loads(item.raw_json or "{}")
                if not isinstance(raw, dict):
                    raw = {}
            except Exception:
                raw = {}
            candidates = [
                raw.get("image"),
                raw.get("image_url"),
                raw.get("cover"),
                raw.get("thumbnail"),
                item.url,
            ]
            for candidate in candidates:
                p = self._normalize_local_path(candidate)
                if p:
                    return p
        return ""

    def _resolve_default_local_cover(self) -> str:
        candidates = [
            settings.DEFAULT_LOCAL_COVER_IMAGE_PATH,
            "./DJI_20240603095231_0001_D_bottom_left.JPG",
        ]
        for candidate in candidates:
            p = self._normalize_local_path(candidate)
            if p:
                return p
        return ""

    def _normalize_local_path(self, value: str | None) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        if v.startswith(("http://", "https://")):
            return ""
        p = Path(v).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists() or not p.is_file():
            return ""
        if p.suffix.lower() not in self.IMAGE_SUFFIX:
            return ""
        return str(p)

    @staticmethod
    def _looks_like_remote_image_ref(value: str) -> bool:
        v = (value or "").strip()
        if not v:
            return False
        p = urlparse(v)
        if p.scheme not in ("http", "https"):
            return False
        path = (p.path or "").lower()
        return path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))

    def _get_draft_or_raise(self, draft_id: int) -> Draft:
        draft = self.db.get(Draft, draft_id)
        if not draft:
            raise ValueError(f"Draft not found: {draft_id}")
        return draft

