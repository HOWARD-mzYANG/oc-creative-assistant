"""后台结构化提取节点（Agent B 第一部分，first_revision 决策 5 + rework 1）。

在 persistence_hub 之后运行：从用户最近的自由对话中提取实体 / 关系，转换成暂存项
（复用 AgentStagingORM）；当 ``auto_apply_staging`` 为 true（工作区流程）时可选
[自动持久化]（accept_all），并向前端推送“新增/更新”的卡片信息，让用户展开编辑或丢弃。
当 ``auto_apply_staging`` 为 false（Chat 模块）时，项目保留为 pending，交给右侧暂存面板。

rework 1 的两个关键点：
1. 自动持久化（仅工作区）：设置 ``auto_apply_staging`` 后，写入 staging 立即 accept_all
   （仍经过 AgentStagingORM + canvas_apply）；前端通过 extraction_applied 事件渲染行内卡片。
2. 按名称去重：如果画布上已经有同名实体，或 staging 中已经有 pending 的同名实体
   （例如 structure_agent 本轮已提出），则跳过 create_node；只有真实节点存在时才通过
   update_node 合并属性。关系使用真实 node_id 或同批次 pending_id 连接。

仅在 ``extraction_enabled`` 为 true 时工作；关闭时为空操作，不影响旧聊天流程。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.memory import format_current_nodes
from app.agents.prompts import load_prompt
from app.agents.structured_call import call_structured
from app.agents.schemas import StructuredExtractionOutput
from app.agents.state import AgentState
from app.db.database import SessionLocal
from app.db.models import AgentStagingORM, ChatSessionORM, NodeORM
from app.llm.factory import get_llm_provider
from app.schemas import AgentStagingCreateItem
from app.services.chat_repository import insert_staging_batch, list_staging_by_batch


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("structured_extractor")

# 实体类型 -> 画布 node_type（与子图分区对齐）。
_NODE_TYPE_BY_ENTITY: dict[str, str] = {
    "character": "character",
    "world": "worldbuilding",
    "plot": "plot",
}

# 关系标签 -> relation_type（驱动画布边样式，并在持久化时使用）。
_RELATION_BY_LABEL: dict[str, str] = {
    "belongs to": "belongs_to",
    "participates in": "belongs_to",
    "mentorship": "belongs_to",
    "nemesis": "conflicts_with",
    "opposes": "conflicts_with",
    "causes": "causes",
    "triggers": "causes",
    "develops into": "develops_into",
}


def _entity_key(node_type: str, title: str) -> tuple[str, str]:
    return (node_type, title.strip().lower())


def _pending_create_refs(db: Session, project_id: str) -> dict[tuple[str, str], str]:
    """为 pending 的 create_node 暂存行建立 (node_type, title) -> pending_id 映射。"""
    refs: dict[tuple[str, str], str] = {}
    rows = db.scalars(
        select(AgentStagingORM).where(
            AgentStagingORM.project_id == project_id,
            AgentStagingORM.status == "pending",
            AgentStagingORM.change_type == "create_node",
        )
    )
    for record in rows:
        payload = record.payload_edited or record.payload or {}
        title = str(payload.get("title") or "").strip()
        if not title:
            continue
        node_type = str(payload.get("node_type") or "character")
        refs[_entity_key(node_type, title)] = record.pending_id or record.id
    return refs


def _merge_content(existing: str, attributes: dict[str, str]) -> str:
    """将新提取的属性合并到已有节点内容中，不重复追加已存在的键值。"""
    lines = [line.strip() for line in (existing or "").splitlines() if line.strip()]
    seen = set(lines)
    for key, value in attributes.items():
        entry = f"{key}: {value}".strip()
        if entry and entry not in seen:
            lines.append(entry)
            seen.add(entry)
    return "\n".join(lines)


def _emit_applied(items: list[dict[str, Any]]) -> None:
    """通过 LangGraph custom stream 将“已持久化卡片”推给前端（非流式调用下静默）。"""
    if not items:
        return
    try:
        writer = get_stream_writer()
    except Exception:
        return
    try:
        writer({"type": "extraction_applied", "items": items})
    except Exception:
        pass


def structured_extractor_node(state: AgentState) -> dict[str, Any]:
    if not state.get("extraction_enabled"):
        return {}

    session_id = state.get("session_id", "")
    project_id = state.get("project_id", "")
    assistant_message_id = state.get("assistant_message_id", "")
    if not (session_id and assistant_message_id):
        return {}

    recent = state.get("recent_messages") or []
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent[-6:]) or "（无）"
    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"[画布引用节点]\n{format_current_nodes(state.get('current_nodes') or [])}\n\n"
            f"[最近对话]\n{history}\n\n[用户最新消息]\n{state.get('user_message', '')}"
        ),
    ]

    out = call_structured(
        get_llm_provider(),
        messages,
        StructuredExtractionOutput,
        label="structured_extractor",
    )
    if out is None:
        return {}

    deferred = [d.model_dump() for d in out.deferred_fields]

    if not out.entities:
        return {"deferred_fields": deferred, "extraction_count": 0}

    items: list[AgentStagingCreateItem] = []
    # 实体名 -> 持久化时引用的 ID（已有 = 真实 node_id，新建 = pending_id）。
    ref_by_name: dict[str, str] = {}
    # 实体名 -> node_type，用于只保留 plot->plot 关系。
    type_by_name: dict[str, str] = {}

    # 去重：画布节点始终参与；pending staging 只在聊天确认模式（auto_apply off）下参与。
    # 工作区自动应用模式中，structure_agent staging 会在本节点运行前被接受；
    # 这里跳过 pending 行可避免 Chat 中重复卡片，但不能阻塞失败的 auto_apply。
    chat_confirm_mode = not state.get("auto_apply_staging")
    with SessionLocal() as db:
        pending_create_refs = _pending_create_refs(db, project_id) if chat_confirm_mode else {}
        pending_seq = 0
        for entity in out.entities:
            node_type = _NODE_TYPE_BY_ENTITY.get(entity.type, "character")
            type_by_name[entity.name] = node_type
            key = _entity_key(node_type, entity.name)
            existing = (
                db.query(NodeORM)
                .filter(
                    NodeORM.project_id == project_id,
                    NodeORM.node_type == node_type,
                    NodeORM.title == entity.name,
                )
                .first()
            )
            if existing is not None:
                # 同名卡片已存在 -> 更新（把新属性合并进内容），不再新建。
                ref_by_name[entity.name] = existing.id
                if entity.attributes:
                    items.append(
                        AgentStagingCreateItem(
                            change_type="update_node",
                            target_id=existing.id,
                            payload={
                                "title": entity.name,
                                "node_type": node_type,
                                "content": _merge_content(existing.content, entity.attributes),
                            },
                            reasoning="后台从对话中补充已有卡片",
                        )
                    )
            elif key in pending_create_refs:
                # structure_agent（或更早的 pending 批次）已经提出过这张卡片。
                ref_by_name[entity.name] = pending_create_refs[key]
            else:
                pending_seq += 1
                pending_id = f"pending-{pending_seq}"
                ref_by_name[entity.name] = pending_id
                content = "; ".join(f"{k}: {v}" for k, v in entity.attributes.items())
                items.append(
                    AgentStagingCreateItem(
                        change_type="create_node",
                        pending_id=pending_id,
                        payload={"title": entity.name, "content": content, "node_type": node_type},
                        reasoning="后台从对话中提取",
                    )
                )

    for relation in out.relations:
        source = ref_by_name.get(relation.source_name)
        target = ref_by_name.get(relation.target_name)
        if not (source and target):
            continue
        if type_by_name.get(relation.source_name) != "plot" \
           or type_by_name.get(relation.target_name) != "plot":
            continue
        relation_type = _RELATION_BY_LABEL.get(relation.label, "relates_to")
        items.append(
            AgentStagingCreateItem(
                change_type="create_edge",
                payload={
                    "source": source,
                    "target": target,
                    "relation_type": relation_type,
                    "label": relation.label or "related",
                },
                reasoning="后台从对话中提取",
            )
        )

    if not items:
        return {"deferred_fields": deferred, "extraction_count": 0}

    with SessionLocal.begin() as db:
        if db.get(ChatSessionORM, session_id) is None:
            return {"deferred_fields": deferred, "extraction_count": 0}
        batch_id, _ = insert_staging_batch(
            db,
            session_id=session_id,
            message_id=assistant_message_id,
            project_id=project_id,
            agent_type="structured_extractor",
            items=items,
        )

    applied: list[dict[str, Any]] = []
    if state.get("auto_apply_staging"):
        applied = _auto_apply(batch_id)
        _emit_applied(applied)

    return {
        "extraction_batch_id": batch_id,
        "extraction_count": len(items),
        "extraction_applied": applied,
        "deferred_fields": deferred,
    }


def _applied_cards_from_batch(batch_id: str) -> list[dict[str, Any]]:
    """从已持久化的 staging 行构建行内卡片 payload（accept_all 后读取 DB）。"""
    with SessionLocal() as db:
        records = list_staging_by_batch(db, batch_id)

    applied: list[dict[str, Any]] = []
    for record in records:
        if record.status not in ("accepted", "edited"):
            continue
        if record.change_type not in ("create_node", "update_node"):
            continue
        if not record.target_id:
            continue
        payload = record.payload_edited or record.payload or {}
        applied.append(
            {
                "node_id": record.target_id,
                "title": str(payload.get("title") or "未命名"),
                "node_type": str(payload.get("node_type") or "character"),
                "content": str(payload.get("content") or ""),
                "change_type": record.change_type,
            }
        )
    return applied


def _auto_apply(batch_id: str) -> list[dict[str, Any]]:
    """自动接受整个暂存批次并持久化，返回“新增/更新”卡片摘要。

    延迟导入 chat_service，避免与 agents 包形成循环依赖（chat_service -> graph -> 本节点）。
    """
    from app.schemas import AgentStagingBatchActionRequest
    from app.services.chat_service import resolve_staging_batch

    try:
        resolve_staging_batch(
            batch_id, AgentStagingBatchActionRequest(action="accept_all")
        )
    except Exception as exc:
        logger.warning("auto_apply failed for batch %s: %s", batch_id, exc)
        return []

    return _applied_cards_from_batch(batch_id)
