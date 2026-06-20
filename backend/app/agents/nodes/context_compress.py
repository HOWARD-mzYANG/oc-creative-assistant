"""Token-budget compression for retrieved context."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.agents.token_budget import count_tokens
from app.core.settings import get_agent_settings
from app.schemas import RagMergedContextItem


def _count_tokens(text: str) -> int:
    """估算文本 token 数，供上下文压缩阈值判断使用。"""
    return count_tokens(text)


def context_compress_node(state: AgentState) -> dict[str, Any]:
    """在检索上下文超出预算时裁剪 merged_context。

    参数：
        state: 当前 agent 图状态，包含待注入的 RAG 合并上下文。

    返回：
        压缩后的 `merged_context` 状态增量；无需压缩时返回空字典。
    """
    items = state.get("merged_context") or []
    if not items:
        return {}

    cap = get_agent_settings().context_token_cap

    kept: list[RagMergedContextItem] = []
    total = 0
    for item in items:
        cost = _count_tokens(f"{item.title}\n{item.content}")
        if total + cost > cap and kept:
            break
        kept.append(item)
        total += cost

    return {"merged_context": kept}
