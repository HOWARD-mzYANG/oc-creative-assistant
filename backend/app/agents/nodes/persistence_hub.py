"""持久化枢纽节点。

每一轮都会用两个独立事务持久化以下副作用：
1. user_message 独立持久化（单独事务）；即使后续 chat_assembler 失败，用户消息也已经提交，
   因而下一轮 recent_messages 不会出现单边缺口。
2. 当 assembler_output 存在时，第二个事务追加 assistant_message；如果本轮 agent 输出包含
   proposed_changes，同一事务会在相同 batch_id 下写入 AgentStaging 记录，等待用户在前端
   暂存面板中接受 / 编辑 / 拒绝。

session 缺失时，整个节点静默跳过，让 graph.invoke 仍能把内存中的 assembler_output 作为兜底
返回给调用方。
"""

from __future__ import annotations

from typing import Any

from app.agents.schemas import ProposedChange
from app.agents.state import AgentState
from app.db.database import SessionLocal
from app.db.models import ChatSessionORM
from app.schemas import AgentStagingCreateItem
from app.services.chat_repository import append_message, insert_staging_batch


_OUTPUT_KEY_BY_INTENT: dict[str, str] = {
    "inspiration": "inspiration_output",
    "research": "research_output",
    "structure": "structure_output",
}
"""只有这三类 agent 会产生 proposed_changes；simulation 物理隔离，不参与。"""


def _collect_proposed_changes(state: AgentState) -> tuple[list[ProposedChange], str]:
    """从与当前意图匹配的 agent 输出中取 proposed_changes；没有则返回空列表。

    agent_type 取 intent.primary，使 staging 表可以按 agent 来源分组展示。
    """
    intent = state.get("intent")
    primary = intent.primary if intent is not None else ""
    output_key = _OUTPUT_KEY_BY_INTENT.get(primary)
    if output_key is None:
        return [], primary

    output = state.get(output_key)
    if output is None:
        return [], primary

    changes = list(getattr(output, "proposed_changes", []) or [])
    return changes, primary


def _to_staging_items(changes: list[ProposedChange]) -> list[AgentStagingCreateItem]:
    """ProposedChange（agent 内部模型）-> AgentStagingCreateItem（持久化模型）。"""
    return [
        AgentStagingCreateItem(
            change_type=change.change_type,
            target_id=change.target_id,
            pending_id=change.pending_id,
            payload=change.payload,
            reasoning=change.reason,
        )
        for change in changes
    ]


def persistence_hub_node(state: AgentState) -> dict[str, Any]:
    session_id = state.get("session_id", "")
    project_id = state.get("project_id", "")
    user_message = state.get("user_message", "").strip()
    assembler = state.get("assembler_output")

    if not session_id:
        return {}

    # 第一事务：用户消息独立持久化，与 assembler 成功/失败解耦。
    with SessionLocal.begin() as db:
        if db.get(ChatSessionORM, session_id) is None:
            return {}
        if user_message:
            append_message(db, session_id=session_id, role="user", content=user_message)

    if assembler is None:
        return {}

    proposed_changes, agent_type = _collect_proposed_changes(state)
    staging_items = _to_staging_items(proposed_changes)

    # 第二事务：assistant_message 与 staging 共用同一事务，
    # 保证消息与批次的引用一致性（staging 行的 message_id 总是指向真实存在的消息）。
    with SessionLocal.begin() as db:
        meta: dict[str, Any] = {
            "agent_type": agent_type,
            "cited_node_ids": list(assembler.cited_node_ids),
            "staging_summary": assembler.staging_summary,
            "web_sources": [item.model_dump() for item in assembler.web_sources],
        }
        assistant_message = append_message(
            db,
            session_id=session_id,
            role="assistant",
            content=assembler.reply_text,
            meta=meta,
        )
        assistant_message_id = assistant_message.id

        batch_id: str | None = None
        if staging_items:
            batch_id, _ = insert_staging_batch(
                db,
                session_id=session_id,
                message_id=assistant_message_id,
                project_id=project_id,
                agent_type=agent_type,
                items=staging_items,
            )

    applied: list[dict[str, Any]] = []
    if batch_id and state.get("auto_apply_staging"):
        from app.agents.nodes.structured_extractor import _auto_apply, _emit_applied
        applied = _auto_apply(batch_id)
        _emit_applied(applied)

    return {
        "assistant_message_id": assistant_message_id,
        "staging_batch_id": batch_id,
        "staging_count": len(staging_items),
        "extraction_applied": applied,
    }
