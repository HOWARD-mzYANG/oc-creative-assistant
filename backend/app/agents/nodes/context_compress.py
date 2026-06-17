"""检索上下文 token 压缩节点。

防止长项目撑爆 LLM 上下文窗口：使用 tiktoken 累加 merged_context 的 token 数；一旦超过
``context_token_cap``，就按当前顺序截断，保留更靠前、更相关的条目。即使单条内容已经超限，也
至少保留第一条，避免把上下文裁成空。
"""

from __future__ import annotations

from typing import Any

import tiktoken

from app.agents.state import AgentState
from app.core.settings import get_agent_settings
from app.schemas import RagMergedContextItem


# cl100k_base 是 GPT-3.5/4、DeepSeek 等主流模型事实上的通用编码；直接使用现成编码，
# 避免每次按模型名解析，也不需要联网下载。
_encoder = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def context_compress_node(state: AgentState) -> dict[str, Any]:
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
