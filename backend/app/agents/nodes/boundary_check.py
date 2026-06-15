"""边界检查节点。

在 chat_assembler 之前运行，对本轮 agent 产出的 proposed_changes 做确定性校验。
它会过滤不合规项目，并把原因记录到 ``boundary_warnings`` 供下游使用，使
chat_assembler 能在回复中如实说明哪些项目被跳过以及原因，避免用户接受空暂存。

校验只执行硬规则，不调用 LLM：
- create_node：title / content 长度，node_type 白名单
- create_edge：source / target 必须是同批次 pending_id 或项目内真实 node_id；禁止自环
- update_node：target_id 必须匹配已有节点，payload 至少包含一个可更新字段
- 整批：pending_id 不得重复，批次变更数量不得超过上限

它与 canvas_apply 的“防御性跳过”配合：canvas_apply 是持久化前的最后兜底，而这里是最早
闸口，让用户能立即在回复中看到“哪一项失败以及为什么”。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.schemas import ProposedChange
from app.agents.state import AgentState
from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.services.graph_mappers import db_parent_id_to_api


# 只有这些意图的 agent 会产生 proposed_changes；simulation 物理隔离，不参与。
_OUTPUT_KEY_BY_INTENT: dict[str, str] = {
    "inspiration": "inspiration_output",
    "research": "research_output",
    "structure": "structure_output",
}

_VALID_NODE_TYPES = {
    "character", "worldbuilding", "plot",
    "idea", "research", "structure",
}
_UPDATABLE_FIELDS = {"title", "content", "node_type", "parent_id", "parentId", "sort_order", "sortOrder"}
_TITLE_MAX = 100
_CONTENT_MAX = 2000
_MAX_CHANGES_PER_BATCH = 15
_AGENTS_WITH_CHANGES = {"inspiration", "research", "structure"}


def boundary_check_node(state: AgentState) -> dict[str, Any]:
    """对与当前意图匹配的 agent 的 proposed_changes 执行边界校验。

    用硬规则过滤不合规项，并把原因记录到 ``boundary_warnings``，供下游 chat_assembler
    引用，让用户立即在回复中看到“哪一项被跳过以及为什么”。
    """
    intent = state.get("intent")
    if intent is None or intent.primary not in _AGENTS_WITH_CHANGES:
        return {}

    output_key = f"{intent.primary}_output"
    output = state.get(output_key)
    if output is None:
        return {}

    changes = list(getattr(output, "proposed_changes", []) or [])
    if not changes:
        return {}

    accepted, warnings = _filter_changes(changes, state.get("project_id", ""))
    if not warnings and len(accepted) == len(changes):
        return {}

    updates: dict[str, Any] = {"boundary_warnings": warnings}
    if len(accepted) != len(changes):
        updates[output_key] = output.model_copy(update={"proposed_changes": accepted})
    return updates


def _filter_changes(
    changes: list[ProposedChange],
    project_id: str,
) -> tuple[list[ProposedChange], list[str]]:
    """运行所有规则并返回（接受的变更，warning 描述列表）。

    去重维度：create_node 按 pending_id，create_edge 按 (source, target, relation_type)
    三元组，update_node 按 (target_id, 关键 payload 字段) 组合。LLM 偶尔会把“一个想好的
    项目”复制 N 次放进列表；这一层会在批次内硬性去重。
    """
    warnings: list[str] = []

    if len(changes) > _MAX_CHANGES_PER_BATCH:
        warnings.append(
            f"Agent 一次提出了 {len(changes)} 项变更，超过每轮上限 "
            f"{_MAX_CHANGES_PER_BATCH}；仅保留前 {_MAX_CHANGES_PER_BATCH} 项。"
        )
        changes = changes[:_MAX_CHANGES_PER_BATCH]

    pending_ids: set[str] = set()
    seen_signatures: set[tuple] = set()
    duplicate_indices: set[int] = set()

    for idx, change in enumerate(changes):
        if change.change_type == "create_node" and change.pending_id:
            if change.pending_id in pending_ids:
                duplicate_indices.add(idx)
                warnings.append(
                    f"create_node #{idx + 1} has pending_id="
                    f"{change.pending_id!r} 与同批次已有项目重复；已跳过。"
                )
            else:
                pending_ids.add(change.pending_id)

        signature = _signature_of(change)
        if signature is None:
            continue
        if signature in seen_signatures:
            duplicate_indices.add(idx)
            warnings.append(
                f"{change.change_type} #{idx + 1} 与同批次已有项目内容相同；已跳过。"
            )
        else:
            seen_signatures.add(signature)

    accepted: list[ProposedChange] = []
    with SessionLocal() as db:
        for idx, change in enumerate(changes):
            if idx in duplicate_indices:
                continue
            problem = _check_one(change, db, project_id, pending_ids)
            if problem is None:
                accepted.append(change)
            else:
                warnings.append(f"{change.change_type} #{idx + 1}: {problem}")

    return accepted, warnings


def _signature_of(change: ProposedChange) -> tuple | None:
    """提取变更的“内容指纹”用于跨项去重；无法形成指纹时返回 None 并跳过去重。"""
    payload = change.payload or {}

    if change.change_type == "create_node":
        return (
            "create_node",
            (str(payload.get("title") or "")).strip().lower(),
            payload.get("node_type"),
            payload.get("parent_id", payload.get("parentId")),
        )

    if change.change_type == "create_edge":
        source = payload.get("source")
        target = payload.get("target")
        relation = payload.get("relation_type") or payload.get("label") or ""
        if not source or not target:
            return None
        return ("create_edge", source, target, relation)

    if change.change_type == "update_node":
        return (
            "update_node",
            change.target_id,
            (str(payload.get("title") or "")).strip().lower(),
            (str(payload.get("content") or "")).strip().lower(),
            payload.get("node_type"),
            payload.get("parent_id", payload.get("parentId")),
            payload.get("sort_order", payload.get("sortOrder")),
        )

    if change.change_type == "delete_node":
        return ("delete_node", change.target_id)

    if change.change_type == "delete_edge":
        return (
            "delete_edge",
            change.target_id,
            payload.get("source"),
            payload.get("target"),
            payload.get("relation_type") or payload.get("label") or "",
        )
    return None


def _check_one(
    change: ProposedChange,
    db: Session,
    project_id: str,
    pending_ids: set[str],
) -> str | None:
    """对单条变更运行所有规则；通过则返回 None，否则返回拒绝原因。"""
    payload = change.payload or {}

    if change.change_type == "create_node":
        title = (str(payload.get("title") or "")).strip()
        if not title:
            return "缺少标题。"
        if len(title) > _TITLE_MAX:
            return f"标题长度 {len(title)} 超过上限 {_TITLE_MAX}。"
        content = str(payload.get("content") or "")
        if len(content) > _CONTENT_MAX:
            return f"内容长度 {len(content)} 超过上限 {_CONTENT_MAX}。"
        if payload.get("node_type") not in _VALID_NODE_TYPES:
            return (
                f"node_type={payload.get('node_type')!r} 不在白名单 "
                f"{sorted(_VALID_NODE_TYPES)} 中。"
            )
        if payload.get("node_type") == "worldbuilding":
            parent_problem = _check_world_parent(
                db,
                project_id,
                _payload_parent_id(payload),
            )
            if parent_problem is not None:
                return parent_problem
        return None

    if change.change_type == "create_edge":
        source = payload.get("source")
        target = payload.get("target")
        if not source or not target:
            return "source 或 target 为空。"
        if source == target:
            return "source 与 target 相同；拒绝自环边。"
        for label, raw in (("source", source), ("target", target)):
            if raw in pending_ids:
                continue
            node = db.get(NodeORM, raw)
            if node is None or node.project_id != project_id:
                return (
                    f"{label}={raw!r} 既不是同批次 pending_id，也不是项目内真实 node_id。"
                )
        return None

    if change.change_type == "update_node":
        if not change.target_id:
            return "缺少 target_id。"
        node = db.get(NodeORM, change.target_id)
        if node is None or node.project_id != project_id:
            return f"target_id={change.target_id!r} 在项目内没有匹配节点。"
        if not any(field in payload for field in _UPDATABLE_FIELDS):
            return f"payload 必须至少包含一个可更新字段 {sorted(_UPDATABLE_FIELDS)}。"
        next_type = str(payload.get("node_type") or node.node_type)
        if next_type == "worldbuilding" and _payload_has_parent(payload):
            parent_id = _payload_parent_id(payload)
            parent_problem = _check_world_parent(
                db,
                project_id,
                parent_id,
                moving_node_id=node.id,
            )
            if parent_problem is not None:
                return parent_problem
            if _world_parent_would_cycle(db, project_id, node.id, parent_id):
                return "parent_id 会形成世界观树循环。"
        return None

    if change.change_type == "delete_node":
        if not change.target_id:
            return "缺少 target_id。"
        node = db.get(NodeORM, change.target_id)
        if node is None or node.project_id != project_id:
            return f"target_id={change.target_id!r} 在项目内没有匹配节点。"
        return None

    if change.change_type == "delete_edge":
        if change.target_id:
            return None  # 真实 edge_id 的项目归属会在 canvas_apply 持久化时再校验。
        payload_src = payload.get("source")
        payload_tgt = payload.get("target")
        if not payload_src or not payload_tgt:
            return "缺少 target_id，或缺少 payload.source / payload.target 三元组。"
        return None

    return f"不支持的 change_type={change.change_type!r}。"


def _payload_parent_id(payload: dict[str, Any]) -> str | None:
    """读取世界观父节点字段，兼容 snake/camel case。"""
    raw = payload.get("parent_id", payload.get("parentId"))
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _payload_has_parent(payload: dict[str, Any]) -> bool:
    """判断 payload 是否显式声明了 parent 字段；空值表示移动到根层级。"""
    return "parent_id" in payload or "parentId" in payload


def _check_world_parent(
    db: Session,
    project_id: str,
    parent_id: str | None,
    *,
    moving_node_id: str | None = None,
) -> str | None:
    """校验 parent_id 可作为世界观父节点；None 表示根层级。"""
    if parent_id is None:
        return None
    if parent_id == moving_node_id:
        return "parent_id 不能指向节点自身。"
    parent = db.get(NodeORM, parent_id)
    if parent is None or parent.project_id != project_id:
        return f"parent_id={parent_id!r} 在项目内没有匹配节点。"
    if parent.node_type != "worldbuilding":
        return f"parent_id={parent_id!r} 不是 worldbuilding 节点。"
    return None


def _world_parent_would_cycle(
    db: Session,
    project_id: str,
    node_id: str,
    parent_id: str | None,
) -> bool:
    """判断世界观节点移动后是否会形成循环。"""
    cursor = parent_id
    visited: set[str] = set()
    while cursor:
        if cursor == node_id:
            return True
        if cursor in visited:
            return True
        visited.add(cursor)
        parent = db.get(NodeORM, cursor)
        if parent is None or parent.project_id != project_id:
            return False
        cursor = db_parent_id_to_api(parent.meta)
    return False
