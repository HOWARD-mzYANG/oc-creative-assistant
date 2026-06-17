"""LLM 结构化输出调用的共享辅助函数。

OpenAI 兼容 provider 偶尔会在 ``with_structured_output`` 中直接返回 ``None`` 而不抛异常；
如果不处理，会导致 agent state 字段为空，并触发 chat_assembler 的通用兜底回复。
"""

from __future__ import annotations

import logging
from typing import TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.llm.provider import LlmProvider


logger = logging.getLogger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)


def call_structured(
    provider: LlmProvider,
    messages: list[BaseMessage],
    schema: type[TSchema],
    *,
    label: str,
) -> TSchema | None:
    """调用结构化输出；失败或结果为空时记录日志并返回 None。"""
    try:
        result = provider.structured(messages, schema)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 结构化调用失败：%s", label, exc)
        return None
    if result is None:
        logger.warning("%s 结构化调用返回 None", label)
    return result
