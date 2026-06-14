"""Web Search client (Tavily).

Design notes:
- Uses Tavily's ``include_answer=advanced`` mode: a single HTTP call returns a
  "model-friendly short answer + source list", with no need for a second LLM
  synthesis, saving a lot of tokens.
- When the api_key is not configured it does not error, but returns
  ``WebSearchUnavailable``, letting the upper-layer tool take the fallback path
  (telling the LLM "web is temporarily unavailable, please answer with existing
  information").
- Error classification: network / authentication / quota are all normalized into
  ``WebSearchError`` subclasses, so the upper layer only decides whether to keep
  retrying based on "whether it is retriable".
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.settings import get_web_search_settings


_TAVILY_ENDPOINT = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebSearchHit:
    """A single search result; fields align with the search_nodes style to keep the LLM's habits consistent."""

    title: str
    url: str
    snippet: str
    score: float


@dataclass(frozen=True)
class WebSearchResponse:
    """Successful response: ``answer`` is the short answer synthesized directly by Tavily, ``hits`` are the raw matches."""

    answer: str
    hits: list[WebSearchHit]


class WebSearchError(RuntimeError):
    """Base class for all recoverable web errors; the message is shown directly to the LLM."""


class WebSearchUnavailable(WebSearchError):
    """The API key is not configured or the service is entirely unavailable; on receiving this the LLM should wrap up immediately and stop retrying."""


def search_web(query: str, top_k: int = 5) -> WebSearchResponse:
    """Call Tavily once and return the normalized results.

    参数：
        query: Search keywords or a natural-language question.
        top_k: Maximum number of results to return, automatically clamped to
            [1, 10].

    抛出：
        WebSearchUnavailable: api_key not configured / Tavily returns 401 or 429.
        WebSearchError: Other network or parsing errors.
    """
    settings = get_web_search_settings()
    if not settings.is_configured:
        raise WebSearchUnavailable("web_search has no API key configured and is temporarily unavailable")

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
        raise WebSearchError(f"web_search network error: {exc}") from exc

    if response.status_code in (401, 403):
        raise WebSearchUnavailable("web_search authentication failed, check OC_WEB_SEARCH_API_KEY")
    if response.status_code == 429:
        raise WebSearchUnavailable("web_search hit a quota limit, please answer with existing information this round")
    if response.status_code >= 400:
        raise WebSearchError(f"web_search HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise WebSearchError("web_search returned invalid JSON") from exc

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