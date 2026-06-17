"""LLM provider 单例工厂。

provider 不会在 import 时构建，而是由调用方按需触发；这样启动时即使缺少 .env，也不会快速失败并拖垮
整个后端。``lru_cache`` 保证每个进程只构建一次，测试代码可以调用
``get_llm_provider.cache_clear()`` 来重置。
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
        f"无法识别的 LLM provider：{settings.provider!r}；仅支持 'openai' | 'mock'"
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
