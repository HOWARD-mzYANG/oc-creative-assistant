"""Retrieval context token compression node.

Prevents long projects from blowing past the LLM's window: uses tiktoken to
accumulate the token count of merged_context, and once it exceeds
``context_token_cap``, truncates in the current order, keeping the earlier,
more relevant items. Even if a single item is over the limit, at least the
first item is kept to avoid trimming everything to empty.
"""

from __future__ import annotations

from typing import Any

from app.agents.token_budget import count_tokens
from app.agents.state import AgentState
from app.core.settings import get_agent_settings
from app.schemas import RagMergedContextItem


def _count_tokens(text: str) -> int:
    return count_tokens(text)


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
