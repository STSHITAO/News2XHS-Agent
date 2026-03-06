from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.search_selector import SearchPlan, select_search_plan

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover
    TavilyClient = None


@dataclass
class SearchItem:
    title: str
    url: str
    content: str
    source: str
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


@dataclass
class SearchResultBundle:
    provider: str
    selected_tool: str
    reasoning: str
    items: list[SearchItem]


class GlobalSearchService:
    def __init__(self) -> None:
        self.provider_type = (settings.SEARCH_TOOL_TYPE or "AnspireAPI").strip()

    def fetch_hot_news(self, query: str, limit: int, period: str = "24h") -> SearchResultBundle:
        plan = select_search_plan(query)
        tool = plan.search_tool
        if period == "week" and tool == "search_news_last_24_hours":
            tool = "search_news_last_week"

        provider = self.provider_type
        reasoning = plan.reasoning
        items: list[SearchItem] = []

        try:
            if self.provider_type == "AnspireAPI":
                items = self._search_anspire(query, limit, tool, plan)
            elif self.provider_type == "BochaAPI":
                items = self._search_bocha(query, limit, tool, plan)
            elif self.provider_type == "TavilyAPI":
                items = self._search_tavily(query, limit, tool, plan)
            else:
                items = self._search_mock(query, limit)
                provider = "MockAPI"
        except Exception as exc:
            # Keep API stable even when third-party providers fail.
            reasoning = f"{plan.reasoning} (external provider failed, auto-fallback to MockAPI: {exc})"
            items = []

        if not items:
            items = self._search_mock(query, min(limit, 8))
            provider = "MockAPI" if provider != "MockAPI" else provider

        return SearchResultBundle(
            provider=provider,
            selected_tool=tool,
            reasoning=reasoning,
            items=items[:limit],
        )

    def _search_anspire(self, query: str, limit: int, tool: str, plan: SearchPlan) -> list[SearchItem]:
        if not settings.ANSPIRE_API_KEY:
            return []

        payload: dict[str, Any] = {
            "query": query,
            "top_k": limit,
            "Insite": "",
            "FromTime": "",
            "ToTime": "",
        }
        now = datetime.now()
        if tool == "search_news_last_24_hours":
            payload["FromTime"] = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            payload["ToTime"] = now.strftime("%Y-%m-%d %H:%M:%S")
        elif tool == "search_news_last_week":
            payload["FromTime"] = (now - timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M:%S")
            payload["ToTime"] = now.strftime("%Y-%m-%d %H:%M:%S")
        elif tool == "search_news_by_date" and plan.start_date and plan.end_date:
            payload["FromTime"] = f"{plan.start_date} 00:00:00"
            payload["ToTime"] = f"{plan.end_date} 23:59:59"

        headers = {
            "Authorization": f"Bearer {settings.ANSPIRE_API_KEY}",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Accept": "*/*",
        }

        with httpx.Client(timeout=settings.QWEN_TIMEOUT) as client:
            # Align with BettaFish-langchain adapter and actual Anspire API behavior.
            response = client.get(settings.ANSPIRE_BASE_URL, headers=headers, params=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get("results") or []
        items: list[SearchItem] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            content = str(row.get("content") or title).strip()
            if not title or not url:
                continue
            items.append(
                SearchItem(
                    title=title,
                    url=url,
                    content=content,
                    source="anspire",
                    published_at=self._parse_datetime(row.get("date")),
                    raw=row,
                )
            )
        return items

    def _search_bocha(self, query: str, limit: int, tool: str, plan: SearchPlan) -> list[SearchItem]:
        if not settings.BOCHA_WEB_SEARCH_API_KEY:
            return []

        payload: dict[str, Any] = {"query": query, "count": limit, "stream": False, "answer": False}
        if tool == "search_news_last_24_hours":
            payload["freshness"] = "oneDay"
        elif tool == "search_news_last_week":
            payload["freshness"] = "oneWeek"
        elif tool == "search_news_by_date" and plan.start_date and plan.end_date:
            payload["start_date"] = plan.start_date
            payload["end_date"] = plan.end_date

        headers = {
            "Authorization": f"Bearer {settings.BOCHA_WEB_SEARCH_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        with httpx.Client(timeout=settings.QWEN_TIMEOUT) as client:
            response = client.post(settings.BOCHA_BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items: list[SearchItem] = []
        for message in data.get("messages") or []:
            if message.get("type") != "source" or message.get("content_type") != "webpage":
                continue
            content_raw = message.get("content") or "{}"
            try:
                content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
            except Exception:
                continue
            for row in content.get("value") or []:
                title = str(row.get("name") or "").strip()
                url = str(row.get("url") or "").strip()
                snippet = str(row.get("snippet") or title).strip()
                if not title or not url:
                    continue
                items.append(
                    SearchItem(
                        title=title,
                        url=url,
                        content=snippet,
                        source="bocha",
                        published_at=self._parse_datetime(row.get("dateLastCrawled")),
                        raw=row,
                    )
                )
        return items

    def _search_tavily(self, query: str, limit: int, tool: str, plan: SearchPlan) -> list[SearchItem]:
        if not settings.TAVILY_API_KEY or TavilyClient is None:
            return []
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        kwargs: dict[str, Any] = {
            "query": query,
            "topic": "general",
            "max_results": limit,
            "search_depth": "basic",
            "include_answer": False,
        }
        if tool == "deep_search_news":
            kwargs["search_depth"] = "advanced"
            kwargs["include_answer"] = "advanced"
            kwargs["max_results"] = min(limit * 2, 20)
        if tool == "search_news_last_24_hours":
            kwargs["time_range"] = "d"
        elif tool == "search_news_last_week":
            kwargs["time_range"] = "w"
        elif tool == "search_news_by_date" and plan.start_date and plan.end_date:
            kwargs["start_date"] = plan.start_date
            kwargs["end_date"] = plan.end_date

        data = client.search(**kwargs)
        items: list[SearchItem] = []
        for row in data.get("results") or []:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            content = str(row.get("content") or title).strip()
            if not title or not url:
                continue
            items.append(
                SearchItem(
                    title=title,
                    url=url,
                    content=content,
                    source="tavily",
                    published_at=self._parse_datetime(row.get("published_date")),
                    raw=row,
                )
            )
        return items

    def _search_mock(self, query: str, limit: int) -> list[SearchItem]:
        now = datetime.now(timezone.utc)
        return [
            SearchItem(
                title=f"[mock] {query} - hotspot clue {idx + 1}",
                url=f"https://example.com/mock-news-{idx + 1}",
                content=f"Mock hotspot content for {query}, for local integration and publish-flow verification.",
                source="mock",
                published_at=now,
                raw={"mock": True, "rank": idx + 1},
            )
            for idx in range(limit)
        ]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            if text.isdigit():
                raw = int(text)
                if raw > 10_000_000_000:
                    raw = raw / 1000
                return datetime.fromtimestamp(raw, tz=timezone.utc)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
