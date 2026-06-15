"""LLM provider singleton factory.

The provider is not constructed at import time; the caller triggers it on demand,
so a missing .env at startup won't fail-fast and take down the whole backend.
``lru_cache`` ensures it's constructed only once per process, and test code can
call ``get_llm_provider.cache_clear()`` to reset it.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.settings import (
    LlmSettings,
    get_llm_settings,
    get_reply_llm_settings,
    has_reply_llm_settings,
)
from app.llm.provider import LlmProvider, MockProvider, OpenAICompatibleProvider


def _build_provider(settings: LlmSettings) -> LlmProvider:
    """根据 LlmSettings 构建真实 provider；主模型和回复模型复用同一套规则。"""
    if settings.provider == "mock":
        return MockProvider()

    if settings.provider == "openai":
        return OpenAICompatibleProvider(settings)

    raise ValueError(
        f"Unrecognized LLM provider: {settings.provider!r}; only 'openai' | 'mock' are supported"
    )


@lru_cache(maxsize=1)
def get_llm_provider() -> LlmProvider:
    return _build_provider(get_llm_settings())


@lru_cache(maxsize=1)
def get_reply_llm_provider() -> LlmProvider:
    """chat_assembler 专用 provider；未配置快模型时直接复用主 provider。"""
    if not has_reply_llm_settings():
        return get_llm_provider()
    return _build_provider(get_reply_llm_settings())
