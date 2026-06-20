"""多层记忆 prompt 组装器。

将 AgentState 中的六类上下文块（world_brief / key_facts / conversation_summary /
recent_messages / current_nodes / merged_context）组装成固定结构摘要，让每个 agent 节点的
HumanMessage 都以同一格式注入背景信息。

升级点（v2）：
- 新增“核心事实层”：由 summary_compress 累积并抽取 key_facts，跨轮不会丢失，避免长对话后
  早期关键设定被滚动摘要覆盖。
- 按意图组装：small_talk 使用精简版本节省 token，其他意图使用完整上下文。
"""

from __future__ import annotations

from app.agents.state import AgentState
from app.schemas import RagCurrentNodePayload, RagMergedContextItem


_RECENT_TRUNCATE = 300
_MERGED_TRUNCATE = 600
_CURRENT_NODE_TRUNCATE = 1200
_KEY_FACTS_MAX = 16


def _truncate(text: str, limit: int) -> str:
    """裁剪单段上下文文本，避免 prompt 片段超过指定字符上限。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_node_body(node: RagCurrentNodePayload, limit: int) -> str:
    """把当前节点正文和结构化字段合并为可注入 prompt 的单行摘要。"""
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
    body = " | ".join(parts) if parts else "（暂无正文）"
    return _truncate(body, limit)


def _format_recent_messages(messages: list[dict]) -> str:
    """格式化最近对话消息，作为多层记忆中的短期上下文。"""
    if not messages:
        return "（无）"
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "?")
        content = _truncate(message.get("content") or "", _RECENT_TRUNCATE)
        lines.append(f"- {role}: {content}")
    return "\n".join(lines)


def _format_merged_context(items: list[RagMergedContextItem]) -> str:
    """格式化 RAG 合并结果，保留节点来源、标题、类型和裁剪后的内容。"""
    if not items:
        return "（无）"
    return "\n".join(
        f"- [{item.id}] {item.title} ({item.type}): "
        f"{_truncate(item.content, _MERGED_TRUNCATE)}"
        for item in items
    )


def _format_current_nodes(nodes: list[RagCurrentNodePayload]) -> str:
    """格式化用户当前引用的节点，支持单节点和多节点两种提示块。"""
    if not nodes:
        return ""
    if len(nodes) == 1:
        node = nodes[0]
        body = _format_node_body(node, _CURRENT_NODE_TRUNCATE)
        return f"【当前节点】\n[{node.id}] {node.title} ({node.type}): {body}"
    lines = [f"【当前节点（共 {len(nodes)} 个，用户希望同时关注它们）】"]
    for node in nodes:
        body = _format_node_body(node, _CURRENT_NODE_TRUNCATE)
        lines.append(f"- [{node.id}] {node.title} ({node.type}): {body}")
    return "\n".join(lines)


def format_current_nodes(nodes: list[RagCurrentNodePayload]) -> str:
    """供 build_memory_block 外部复用的引用节点块包装函数。"""
    section = _format_current_nodes(nodes)
    return section if section else "（没有引用节点）"


def _format_key_facts(facts: list[str]) -> str:
    """累积核心事实，仅保留最近的 _KEY_FACTS_MAX 条，避免无界增长。"""
    if not facts:
        return "（尚未积累）"
    tail = facts[-_KEY_FACTS_MAX:]
    return "\n".join(f"- {fact}" for fact in tail)


def build_memory_block(state: AgentState, intent: str | None = None) -> str:
    """根据意图选择性组装多层记忆片段。

    small_talk 只需要世界观概要和最近对话，不需要画布检索结果或核心事实层；这样能节省 token，
    并避免 LLM 在闲聊回复中误用项目角色名。其他意图使用完整上下文。
    """
    world_brief = (state.get("world_brief") or "").strip()
    seed_context = (state.get("seed_context") or "").strip()
    key_facts = state.get("key_facts") or []
    summary = (state.get("conversation_summary") or "").strip()
    recent = state.get("recent_messages") or []
    merged = state.get("merged_context") or []
    current_node_section = _format_current_nodes(state.get("current_nodes") or [])

    seed_section = f"【项目 Seed（当前全貌快照）】\n{seed_context}" if seed_context else ""

    if intent == "small_talk":
        sections = [f"【世界观概要】\n{world_brief or '（尚未积累）'}"]
        if seed_section:
            sections.append(seed_section)
        sections.append(f"【最近对话】\n{_format_recent_messages(recent)}")
        if current_node_section:
            sections.append(current_node_section)
        return "\n\n".join(sections)

    sections = [
        f"【世界观概要】\n{world_brief or '（尚未积累）'}",
    ]
    if seed_section:
        sections.append(seed_section)
    sections += [
        f"【核心事实层（跨轮累积，不会被摘要覆盖）】\n{_format_key_facts(key_facts)}",
        f"【过往对话摘要】\n{summary or '（无）'}",
        f"【最近对话】\n{_format_recent_messages(recent)}",
        f"【画布相关节点】\n{_format_merged_context(merged)}",
    ]
    if current_node_section:
        sections.append(current_node_section)
    return "\n\n".join(sections)
