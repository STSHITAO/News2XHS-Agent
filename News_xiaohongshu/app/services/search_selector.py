from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel

from app.core.config import settings

TOOL_TYPES = Literal[
    "basic_search_news",
    "deep_search_news",
    "search_news_last_24_hours",
    "search_news_last_week",
    "search_news_by_date",
]


@dataclass
class SearchPlan:
    search_tool: str
    reasoning: str
    start_date: str | None = None
    end_date: str | None = None


class SearchPlanOutput(BaseModel):
    search_tool: TOOL_TYPES
    reasoning: str
    start_date: str | None = None
    end_date: str | None = None


class AgentState(TypedDict, total=False):
    query: str
    fallback_plan: SearchPlan
    llm_plan: SearchPlan | None
    final_plan: SearchPlan


_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_VALID_TOOLS: set[str] = {
    "basic_search_news",
    "deep_search_news",
    "search_news_last_24_hours",
    "search_news_last_week",
    "search_news_by_date",
}


def _extract_dates(text: str) -> tuple[str | None, str | None]:
    matches = _DATE_PATTERN.findall(text or "")
    if len(matches) >= 2:
        return matches[0], matches[1]
    if len(matches) == 1:
        return matches[0], matches[0]
    return None, None


def _valid_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def _normalize_plan(raw: SearchPlan) -> SearchPlan:
    tool = (raw.search_tool or "").strip()
    if tool not in _VALID_TOOLS:
        tool = "basic_search_news"

    start_date = raw.start_date if _valid_date(raw.start_date) else None
    end_date = raw.end_date if _valid_date(raw.end_date) else None

    if tool == "search_news_by_date":
        if not start_date and end_date:
            start_date = end_date
        if not end_date and start_date:
            end_date = start_date
        if not start_date or not end_date:
            tool = "basic_search_news"

    return SearchPlan(
        search_tool=tool,
        reasoning=(raw.reasoning or "").strip() or "Fallback routing decision.",
        start_date=start_date,
        end_date=end_date,
    )


def _fallback_plan(query: str) -> SearchPlan:
    lowered = (query or "").lower()
    start_date, end_date = _extract_dates(query)
    if _valid_date(start_date) and _valid_date(end_date):
        return SearchPlan(
            search_tool="search_news_by_date",
            reasoning="Detected explicit date range in query.",
            start_date=start_date,
            end_date=end_date,
        )

    cn_latest = ["24小时", "今天", "最新", "近一天"]
    cn_week = ["本周", "一周", "近7天", "近七天"]
    cn_deep = ["深度", "全面", "分析", "复盘"]

    if _contains_any(lowered, ["24h", "today", "latest"]) or _contains_any(query, cn_latest):
        return SearchPlan("search_news_last_24_hours", "Query is highly time-sensitive.")
    if _contains_any(lowered, ["week", "last week", "7d"]) or _contains_any(query, cn_week):
        return SearchPlan("search_news_last_week", "Query asks for week-level timeline.")
    if _contains_any(lowered, ["deep", "analysis", "comprehensive"]) or _contains_any(query, cn_deep):
        return SearchPlan("deep_search_news", "Query needs deeper coverage.")
    return SearchPlan("basic_search_news", "Default broad web-news search.")


class SearchPlanAgent:
    """LangChain + LangGraph based search-tool routing agent."""

    def __init__(self) -> None:
        self._llm = self._build_llm()
        self._graph = self._build_graph()

    @staticmethod
    def _build_llm():
        if not settings.ENABLE_FUNCTION_CALLING:
            return None
        if not (settings.QWEN_API_KEY and settings.QWEN_BASE_URL and settings.QWEN_MODEL):
            return None

        try:
            from langchain_openai import ChatOpenAI
        except Exception:
            return None

        extra_body = None
        qwen_model = (settings.QWEN_MODEL or "").lower()
        qwen_base_url = (settings.QWEN_BASE_URL or "").lower()
        if "qwen3" in qwen_model or "modelscope.cn" in qwen_base_url:
            extra_body = {"enable_thinking": False}

        return ChatOpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_BASE_URL,
            model=settings.QWEN_MODEL,
            temperature=0,
            timeout=settings.QWEN_TIMEOUT,
            extra_body=extra_body,
            max_retries=0,
        )

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        graph = StateGraph(AgentState)
        graph.add_node("fallback", self._fallback_node)
        graph.add_node("llm_router", self._llm_router_node)
        graph.add_node("finalize", self._finalize_node)

        graph.add_edge(START, "fallback")
        graph.add_edge("fallback", "llm_router")
        graph.add_edge("llm_router", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    @staticmethod
    def _fallback_node(state: AgentState) -> AgentState:
        plan = _fallback_plan(state.get("query", ""))
        return {"fallback_plan": _normalize_plan(plan)}

    def _llm_router_node(self, state: AgentState) -> AgentState:
        if self._llm is None:
            return {"llm_plan": None}

        query = state.get("query", "")
        system_prompt = (
            "You are a routing agent for news search tools. "
            "Select exactly one tool and optional date args. "
            "Dates must be valid YYYY-MM-DD."
        )
        user_prompt = f"search_query={query}"

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            parser = self._llm.with_structured_output(SearchPlanOutput)
            output = parser.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            llm_plan = SearchPlan(
                search_tool=output.search_tool,
                reasoning=output.reasoning,
                start_date=output.start_date,
                end_date=output.end_date,
            )
            return {"llm_plan": _normalize_plan(llm_plan)}
        except Exception:
            return {"llm_plan": None}

    @staticmethod
    def _finalize_node(state: AgentState) -> AgentState:
        fallback = state.get("fallback_plan") or _normalize_plan(_fallback_plan(state.get("query", "")))
        llm_plan = state.get("llm_plan")
        final = llm_plan if llm_plan is not None else fallback
        return {"final_plan": _normalize_plan(final)}

    def select(self, query: str) -> SearchPlan:
        if self._graph is None:
            return _normalize_plan(_fallback_plan(query))
        try:
            result = self._graph.invoke({"query": query})
            if isinstance(result, dict) and isinstance(result.get("final_plan"), SearchPlan):
                return result["final_plan"]
        except Exception:
            pass
        return _normalize_plan(_fallback_plan(query))


_AGENT: SearchPlanAgent | None = None


def _get_agent() -> SearchPlanAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = SearchPlanAgent()
    return _AGENT


def select_search_plan(query: str) -> SearchPlan:
    return _get_agent().select(query)
