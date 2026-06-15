"""Multi-layer memory prompt assembler.

Assembles the six context blocks in AgentState (world_brief / key_facts /
conversation_summary / recent_messages / current_nodes / merged_context) into a
fixed-structure brief, so every agent node's HumanMessage injects background
information in the same format.

Upgrades (v2):
- Added a "core facts layer": key_facts accumulated and extracted by
  summary_compress, never lost across turns, preventing early key settings from
  being overwritten by the rolling summary after a long conversation
- intent-aware assembly: small_talk uses a trimmed version to save tokens, while
  the other intents use the full set
"""

from __future__ import annotations

from app.agents.state import AgentState
from app.schemas import RagCurrentNodePayload, RagMergedContextItem


_RECENT_TRUNCATE = 300
_MERGED_TRUNCATE = 600
_CURRENT_NODE_TRUNCATE = 1200
_KEY_FACTS_MAX = 16


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_node_body(node: RagCurrentNodePayload, limit: int) -> str:
    parts: list[str] = []
    content = (node.content or "").strip()
    if content:
        parts.append(content)
    fields = node.fields or {}
    if fields:
        field_text = "; ".join(
            f"{key}: {value}" for key, value in fields.items() if str(value).strip()
        )
        if field_text:
            parts.append(field_text)
    body = " | ".join(parts) if parts else "(no body yet)"
    return _truncate(body, limit)


def _format_recent_messages(messages: list[dict]) -> str:
    if not messages:
        return "(none)"
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "?")
        content = _truncate(message.get("content") or "", _RECENT_TRUNCATE)
        lines.append(f"- {role}: {content}")
    return "\n".join(lines)


def _format_merged_context(items: list[RagMergedContextItem]) -> str:
    if not items:
        return "(none)"
    return "\n".join(
        f"- [{item.id}] {item.title} ({item.type}): "
        f"{_truncate(item.content, _MERGED_TRUNCATE)}"
        for item in items
    )


def _format_current_nodes(nodes: list[RagCurrentNodePayload]) -> str:
    if not nodes:
        return ""
    if len(nodes) == 1:
        node = nodes[0]
        body = _format_node_body(node, _CURRENT_NODE_TRUNCATE)
        return f"【Current Node】\n[{node.id}] {node.title} ({node.type}): {body}"
    lines = [f"【Current Nodes ({len(nodes)} total, the user wants to focus on all of them)】"]
    for node in nodes:
        body = _format_node_body(node, _CURRENT_NODE_TRUNCATE)
        lines.append(f"- [{node.id}] {node.title} ({node.type}): {body}")
    return "\n".join(lines)


def format_current_nodes(nodes: list[RagCurrentNodePayload]) -> str:
    """Public wrapper for quoted-node blocks outside build_memory_block."""
    section = _format_current_nodes(nodes)
    return section if section else "(no quoted nodes)"


def _format_key_facts(facts: list[str]) -> str:
    """Accumulated core facts, keeping only the most recent _KEY_FACTS_MAX entries to avoid unbounded growth."""
    if not facts:
        return "(nothing accumulated yet)"
    tail = facts[-_KEY_FACTS_MAX:]
    return "\n".join(f"- {fact}" for fact in tail)


def build_memory_block(state: AgentState, intent: str | None = None) -> str:
    """Selectively assemble multi-layer memory sections by intent.

    small_talk only needs the worldbuilding outline + recent conversation, not
    the canvas retrieval results or the core facts layer, which saves tokens and
    keeps the LLM from misusing project character names in chit-chat replies.
    Other intents use the full set.
    """
    world_brief = (state.get("world_brief") or "").strip()
    seed_context = (state.get("seed_context") or "").strip()
    key_facts = state.get("key_facts") or []
    summary = (state.get("conversation_summary") or "").strip()
    recent = state.get("recent_messages") or []
    merged = state.get("merged_context") or []
    current_node_section = _format_current_nodes(state.get("current_nodes") or [])

    seed_section = f"【Project Seed (snapshot of the current full picture)】\n{seed_context}" if seed_context else ""

    if intent == "small_talk":
        sections = [f"【Worldbuilding Outline】\n{world_brief or '(nothing accumulated yet)'}"]
        if seed_section:
            sections.append(seed_section)
        sections.append(f"【Recent Conversation】\n{_format_recent_messages(recent)}")
        if current_node_section:
            sections.append(current_node_section)
        return "\n\n".join(sections)

    sections = [
        f"【Worldbuilding Outline】\n{world_brief or '(nothing accumulated yet)'}",
    ]
    if seed_section:
        sections.append(seed_section)
    sections += [
        f"【Core Facts Layer (accumulated across turns, never overwritten by the summary)】\n{_format_key_facts(key_facts)}",
        f"【Past Conversation Summary】\n{summary or '(none)'}",
        f"【Recent Conversation】\n{_format_recent_messages(recent)}",
        f"【Canvas-Related Nodes】\n{_format_merged_context(merged)}",
    ]
    if current_node_section:
        sections.append(current_node_section)
    return "\n\n".join(sections)
