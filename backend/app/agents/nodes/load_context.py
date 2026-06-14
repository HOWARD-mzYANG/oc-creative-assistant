"""读取会话元数据、最近消息和当前节点，并写入 AgentState 的记忆与上下文字段。

该节点是图的“入口加载器”；后续 RAG / agent 节点都依赖它写入的快照。``world_brief``
来自项目级 ProjectORM，使多轮对话共享同一份世界观上下文；``recent_message_window`` 与
summary_compress 节点的 ``keep_recent`` 协同决定哪些消息“原样喂入”，哪些进入摘要。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.agents.state import AgentState
from app.core.settings import get_agent_settings
from app.db.database import SessionLocal
from app.db.models import ChatMessageORM, ChatSessionORM, NodeORM, ProjectORM, ProjectSeedORM
from app.indexing.document_loader import node_to_current_payload


def _empty_context() -> dict[str, Any]:
    """为所有“可能跨轮残留”的 AgentState 字段返回清零 delta。

    两条返回路径（session 缺失 / 正常加载）都从这些零值开始，避免 LangGraph 复用 checkpoint
    时上一轮的 *_output 或 boundary_warnings 污染本轮 assembler 输入。
    """
    return {
        "world_brief": "",
        "seed_context": "",
        "conversation_summary": "",
        "key_facts": [],
        "recent_messages": [],
        "current_nodes": [],
        "intent": None,
        "inspiration_output": None,
        "research_output": None,
        "structure_output": None,
        "simulation_output": None,
        "assembler_output": None,
        "boundary_warnings": [],
        "staging_batch_id": None,
        "staging_count": 0,
        "next_question_hint": "",
        "deferred_fields": [],
        "extraction_batch_id": None,
        "extraction_count": 0,
        "extraction_applied": [],
    }


def load_context_node(state: AgentState) -> dict[str, Any]:
    """从 SQLite 拉取上下文；session 缺失或未提供时返回空骨架。"""
    session_id = state.get("session_id", "")
    selected_ids = state.get("selected_node_ids") or []

    if not session_id:
        return _empty_context()

    window = get_agent_settings().recent_message_window

    with SessionLocal() as db:
        session = db.get(ChatSessionORM, session_id)
        if session is None:
            return _empty_context()

        project = db.get(ProjectORM, session.project_id)
        world_brief = project.world_brief if project is not None else ""

        # 最新项目 seed（决策 4）：启动时注入的低成本全项目快照。
        latest_seed = (
            db.query(ProjectSeedORM)
            .filter(ProjectSeedORM.project_id == session.project_id)
            .order_by(ProjectSeedORM.version.desc())
            .first()
        )
        seed_context = latest_seed.seed_json if latest_seed is not None else ""

        recent = list(
            db.scalars(
                select(ChatMessageORM)
                .where(ChatMessageORM.session_id == session_id)
                .order_by(ChatMessageORM.created_at.desc())
                .limit(window)
            )
        )
        # SQL 为了 LIMIT 按倒序取数；喂给 prompt 前再翻回时间正序。
        recent.reverse()

        current_node_payloads: list[Any] = []
        for node_id in selected_ids:
            node = db.get(NodeORM, node_id)
            if node is not None:
                current_node_payloads.append(node_to_current_payload(node))

        return {
            **_empty_context(),
            "world_brief": world_brief,
            "seed_context": seed_context,
            "conversation_summary": session.conversation_summary,
            "key_facts": list(session.key_facts or []),
            "recent_messages": [
                {"role": message.role, "content": message.content} for message in recent
            ],
            "current_nodes": current_node_payloads,
        }
