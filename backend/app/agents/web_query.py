"""外部联网研究问题的启发式判断与预取辅助函数。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from langchain_core.messages import BaseMessage, ToolMessage

from app.agents.schemas import WebSourceItem
from app.services.web_search_client import (
    WebSearchError,
    WebSearchUnavailable,
    WebSearchHit,
    search_web,
)


logger = logging.getLogger(__name__)

MAX_WEB_SOURCE_CARDS = 3

_WEB_QUERY_FRAGMENTS = (
    "天气",
    "weather",
    "下雨",
    "降雨",
    "气温",
    "forecast",
    "会不会下",
    "新闻",
    "news",
    "实时",
    "联网",
    "上网",
    "网上查",
    "搜一下",
    "查一下",
    "历史上",
    "史实",
    "真实世界",
    "现实世界",
    "longsword",
    "medieval",
)

_PROJECT_SCOPED_FRAGMENTS = (
    "项目里",
    "项目内",
    "画布",
    "情节节点",
    "我的故事",
    "世界观节点",
    "看得到",
    "有哪些角色",
    "有哪些情节",
    "plot node",
    "my story",
    "my project",
)

_EXTERNAL_TIME_SIGNALS = (
    "今天",
    "今日",
    "本月",
    "今年",
    "7月",
    "月份",
    "today",
    "this month",
    "会不会",
    "实时",
)


@dataclass(frozen=True)
class WebPrefetchResult:
    block: str
    fallback_answer: str
    sources: list[WebSourceItem]


def resolve_web_search_enabled(message: str, mode: str) -> bool:
    """结合用户开关（auto/on/off）和自动检测启发式判断是否启用联网搜索。"""
    normalized = (mode or "auto").strip().lower()
    if normalized == "on":
        return True
    if normalized == "off":
        return False
    return looks_like_web_query(message)


def web_search_mode_label(mode: str) -> str:
    """把前端 web search 模式值转换为 trace 中展示的短标签。"""
    normalized = (mode or "auto").strip().lower()
    if normalized == "on":
        return "force on"
    if normalized == "off":
        return "off"
    return "auto"


def looks_like_web_query(message: str) -> bool:
    """当用户明显需要 Tavily / web_search，而不只是项目 RAG 时返回 True。"""
    raw = message.strip()
    if not raw:
        return False
    lower = raw.lower()
    has_web = any(frag in raw or frag in lower for frag in _WEB_QUERY_FRAGMENTS)
    if not has_web:
        return False
    if any(frag in raw for frag in _PROJECT_SCOPED_FRAGMENTS):
        return any(sig in raw or sig in lower for sig in _EXTERNAL_TIME_SIGNALS)
    return True


def hits_to_sources(hits: list[WebSearchHit], *, limit: int = MAX_WEB_SOURCE_CARDS) -> list[WebSourceItem]:
    """把搜索命中结果转换为前端来源卡片，并按 URL 去重限量。"""
    sources: list[WebSourceItem] = []
    seen: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append(
            WebSourceItem(
                title=(hit.title or _host_label(url)).strip(),
                url=url,
                snippet=hit.snippet[:300].replace("\n", " "),
            )
        )
        if len(sources) >= limit:
            break
    return sources


def _host_label(url: str) -> str:
    """从 URL 提取可读域名，作为缺失标题时的回退标签。"""
    try:
        host = urlparse(url).netloc or url
    except ValueError:
        host = url
    return host.removeprefix("www.")


def merge_web_sources(*groups: list[WebSourceItem], limit: int = MAX_WEB_SOURCE_CARDS) -> list[WebSourceItem]:
    """合并多组来源卡片，按 URL 去重并保留先出现的来源。"""
    merged: list[WebSourceItem] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            url = item.url.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def prefetch_web_search(query: str, *, top_k: int = 5) -> WebPrefetchResult | None:
    """调用一次 Tavily；返回 prompt 块、兜底答案和链接卡片。"""
    try:
        response = search_web(query, top_k=top_k)
    except WebSearchUnavailable as exc:
        logger.warning("web_search unavailable during prefetch: %s", exc)
        return None
    except WebSearchError as exc:
        logger.warning("web_search error during prefetch: %s", exc)
        return None

    answer = (response.answer or "").strip()
    sources = hits_to_sources(response.hits)
    lines = [f"answer: {answer or '(没有综合答案)'}"]
    for index, item in enumerate(sources, start=1):
        lines.append(f"{index}. {item.title} — {item.snippet[:240]}")
    block = "\n".join(lines)
    fallback = answer or (sources[0].snippet[:400] if sources else "")
    return WebPrefetchResult(block=block, fallback_answer=fallback, sources=sources)


def extract_web_sources_from_tool_history(
    history: list[BaseMessage],
    *,
    limit: int = MAX_WEB_SOURCE_CARDS,
) -> list[WebSourceItem]:
    """从 ReAct 历史中解析 web_search 工具返回的 JSON 来源。"""
    sources: list[WebSourceItem] = []
    seen: set[str] = set()

    for message in history:
        if not isinstance(message, ToolMessage):
            continue
        raw = message.content if isinstance(message.content, str) else str(message.content)
        stripped = raw.strip()
        if not stripped.startswith("{"):
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if "hits" not in data:
            continue
        for hit in data.get("hits") or []:
            url = str(hit.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                WebSourceItem(
                    title=str(hit.get("title") or _host_label(url)).strip(),
                    url=url,
                    snippet=str(hit.get("snippet") or "")[:300],
                )
            )
            if len(sources) >= limit:
                return sources
    return sources
