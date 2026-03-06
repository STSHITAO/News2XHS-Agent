from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import HotTopic, NewsItem
from app.services.search_service import GlobalSearchService, SearchResultBundle
from app.utils.text_sanitize import sanitize_topic


class NewsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.search_service = GlobalSearchService()

    def fetch_and_store_hot_news(self, query: str, limit: int, period: str = "24h") -> SearchResultBundle:
        clean_query = sanitize_topic(query, max_len=24)
        bundle = self.search_service.fetch_hot_news(query=clean_query, limit=limit, period=period)
        topic = HotTopic(
            keyword=clean_query,
            source=bundle.provider,
            score=len(bundle.items),
            captured_at=datetime.now(timezone.utc),
        )
        self.db.add(topic)
        self.db.flush()

        for item in bundle.items:
            url_key = self._build_url_key(item.url)
            existing = self.db.scalar(select(NewsItem).where(NewsItem.url_key == url_key))
            if existing:
                existing.summary = item.content
                existing.source = item.source
                existing.published_at = item.published_at
                existing.raw_json = json.dumps(item.raw or {}, ensure_ascii=False)
                existing.topic_id = topic.id
                existing.url = item.url[:1024]
                continue

            row = NewsItem(
                topic_id=topic.id,
                title=item.title,
                url=item.url[:1024],
                url_key=url_key,
                summary=item.content,
                source=item.source,
                published_at=item.published_at,
                raw_json=json.dumps(item.raw or {}, ensure_ascii=False),
            )
            self.db.add(row)

        self.db.commit()
        return bundle

    def list_hot_news(self, limit: int = 50) -> list[NewsItem]:
        stmt = select(NewsItem).order_by(desc(NewsItem.created_at)).limit(limit)
        return list(self.db.scalars(stmt).all())

    @staticmethod
    def _build_url_key(url: str) -> str:
        return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()
