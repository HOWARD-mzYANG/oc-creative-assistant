"""Web Search 客户端（Tavily）。

设计说明：
- 使用 Tavily 的 ``include_answer=advanced`` 模式：一次 HTTP 调用即可返回
  “适合模型使用的短答案 + 来源列表”，不需要再调用第二个 LLM 做综合，节省大量 token。
- api_key 未配置时不直接崩溃，而是抛出 ``WebSearchUnavailable``，让上层工具走降级路径
  （提示 LLM“联网暂时不可用，请基于已有信息回答”）。
- 错误分类：网络 / 鉴权 / 配额问题都会归一化为 ``WebSearchError`` 子类，上层只需要根据
  “是否值得重试”决定后续处理。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.settings import get_web_search_settings


_TAVILY_ENDPOINT = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebSearchHit:
    """单条搜索结果；字段风格与 search_nodes 对齐，保持 LLM 使用习惯一致。"""

    title: str
    url: str
    snippet: str
    score: float


@dataclass(frozen=True)
class WebSearchResponse:
    """成功响应：``answer`` 是 Tavily 直接综合的短答案，``hits`` 是原始命中结果。"""

    answer: str
    hits: list[WebSearchHit]


class WebSearchError(RuntimeError):
    """所有可恢复联网错误的基类；错误消息会直接展示给 LLM。"""


class WebSearchUnavailable(WebSearchError):
    """API key 未配置或服务整体不可用；收到后 LLM 应立即收束并停止重试。"""


def search_web(query: str, top_k: int = 5) -> WebSearchResponse:
    """调用一次 Tavily 并返回归一化结果。

    参数：
        query: 搜索关键词或自然语言问题。
        top_k: 最多返回多少条结果，会自动限制到 [1, 10]。

    抛出：
        WebSearchUnavailable: api_key 未配置，或 Tavily 返回 401 / 429。
        WebSearchError: 其他网络或解析错误。
    """
    settings = get_web_search_settings()
    if not settings.is_configured:
        raise WebSearchUnavailable("web_search 未配置 API key，暂时不可用")

    bounded_top_k = max(1, min(int(top_k), 10))
    payload = {
        "api_key": settings.api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": "advanced",
        "max_results": bounded_top_k,
    }

    try:
        with httpx.Client(timeout=settings.timeout_seconds) as client:
            response = client.post(_TAVILY_ENDPOINT, json=payload)
    except httpx.HTTPError as exc:
        raise WebSearchError(f"web_search 网络错误：{exc}") from exc

    if response.status_code in (401, 403):
        raise WebSearchUnavailable("web_search 鉴权失败，请检查 OC_WEB_SEARCH_API_KEY")
    if response.status_code == 429:
        raise WebSearchUnavailable("web_search 触发配额限制，本轮请基于已有信息回答")
    if response.status_code >= 400:
        raise WebSearchError(f"web_search HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise WebSearchError("web_search 返回了无效 JSON") from exc

    hits = [
        WebSearchHit(
            title=str(item.get("title", "")),
            url=str(item.get("url", "")),
            snippet=str(item.get("content", ""))[:400],
            score=float(item.get("score") or 0.0),
        )
        for item in (data.get("results") or [])
    ]
    return WebSearchResponse(
        answer=str(data.get("answer", "")).strip(),
        hits=hits,
    )
