"""将已确认的暂存记录应用到画布。

调用方负责把暂存状态推进到 ``accepted`` / ``edited``；本模块只负责把 payload
转换为 NodeORM/EdgeORM，并在同一事务内 flush 到 SQLite。

支持的变更类型：
- ``create_node``：写入 NodeORM，并标记为 AI 来源；同批次内的 pending_id
  由调用方在返回时累积到 ``pending_id_map``；生成的 node_id 也会写回
  ``record.target_id``，使跨 HTTP 请求单条接受 create_edge / world parent_id
  时能从 DB 找回映射。
- ``create_edge``：写入 EdgeORM；source / target 可以是真实 node_id，也可以是
  同批次 create_node 的 pending_id；当端点无效或由 LLM 捏造时静默跳过，避免
  SQLite 外键约束导致事务炸掉。

ChromaDB 同步必须发生在事务提交后，因此本模块只返回新写入的 node_id；调用方在
事务关闭后再对每个节点触发 ``safe_sync_node_index``。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.database import _SECTION_BY_NODE_TYPE, _DEFAULT_SECTION
from app.db.models import AgentStagingORM, EdgeORM, NodeORM, ProjectORM
from app.services.graph_mappers import (
    api_meta_to_db,
    db_meta_to_api,
    db_parent_id_to_api,
    db_sort_order_to_api,
    db_status_to_api,
    db_tags_to_api,
)
from app.services.node_layout import find_free_node_position

logger = logging.getLogger(__name__)


_ACCEPTED_STATUSES = {"accepted", "edited"}

# section -> ProjectORM 上对应的 graph_id 属性名。
_GRAPH_ID_ATTR_BY_SECTION = {
    "plot": "plot_graph_id",
    "character": "character_graph_id",
    "world": "world_graph_id",
}


def _resolve_graph_id(db: Session, project_id: str, node_type: str) -> str | None:
    """根据 node_type 查找节点应归属的子图 ID（first_revision 决策 1）。

    如果项目尚未迁移到子图（理论上不应发生），返回 None，此时节点降级为没有
    graph_id。
    """
    project = db.get(ProjectORM, project_id)
    if project is None:
        return None
    section = _SECTION_BY_NODE_TYPE.get(node_type, _DEFAULT_SECTION)
    return getattr(project, _GRAPH_ID_ATTR_BY_SECTION[section], None)


def _payload_parent_id(payload: dict[str, Any]) -> str | None:
    """读取 staging payload 中的世界观父节点字段，兼容 snake/camel case。"""
    raw = payload.get("parent_id", payload.get("parentId"))
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _resolve_world_parent_id(
    payload: dict[str, Any],
    pending_id_map: dict[str, str],
) -> str | None:
    """把 worldbuilding parent_id 从同批次 pending_id 解析成真实 node_id。"""
    parent_id = _payload_parent_id(payload)
    if parent_id in pending_id_map:
        return pending_id_map[parent_id]
    return parent_id


def _payload_has_parent(payload: dict[str, Any]) -> bool:
    """区分“未传 parent 字段”和“显式移动到根层级”。"""
    return "parent_id" in payload or "parentId" in payload


def _payload_sort_order(payload: dict[str, Any]) -> int | None:
    """读取 staging payload 中的排序字段，兼容 snake/camel case。"""
    raw = payload.get("sort_order", payload.get("sortOrder"))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _validate_world_parent(
    db: Session,
    project_id: str,
    parent_id: str | None,
    *,
    exclude_node_id: str | None = None,
) -> str | None:
    """校验世界观父节点存在且不会形成自引用；失败时返回 None。"""
    if parent_id is None:
        return None
    if parent_id == exclude_node_id:
        return None

    parent = db.get(NodeORM, parent_id)
    if parent is None or parent.project_id != project_id or parent.node_type != "worldbuilding":
        return None
    return parent_id


def _next_world_sort_order(db: Session, project_id: str, parent_id: str | None) -> int:
    """计算世界观某个父节点下的下一个排序值。"""
    max_order = -1
    nodes = (
        db.query(NodeORM)
        .filter(NodeORM.project_id == project_id, NodeORM.node_type == "worldbuilding")
        .all()
    )
    for node in nodes:
        if db_parent_id_to_api(node.meta) != parent_id:
            continue
        max_order = max(max_order, db_sort_order_to_api(node.meta))
    return max_order + 1


def _world_parent_would_cycle(
    db: Session,
    project_id: str,
    node_id: str,
    parent_id: str | None,
) -> bool:
    """判断把 node_id 放到 parent_id 下是否会形成世界观树循环。"""
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


def _set_world_hierarchy_meta(
    node: NodeORM,
    *,
    parent_id: str | None,
    sort_order: int,
) -> None:
    """把世界观树层级写入 node.meta，保持与前端保存格式一致。"""
    node.meta = api_meta_to_db(
        db_meta_to_api(node.meta),
        db_tags_to_api(node.meta),
        db_status_to_api(node.meta),
        existing_meta=node.meta,
        parent_id=parent_id,
        sort_order=sort_order,
    )


def apply_staging_record(
    db: Session,
    record: AgentStagingORM,
    pending_id_map: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """将单条暂存记录应用到画布。

    返回：
        (upserted_node_id, deleted_node_id) 元组：
        - upserted_node_id：create_node / update_node 持久化后的真实 ID，调用方
          在事务关闭后用它触发 ChromaDB 重新嵌入；
        - deleted_node_id：delete_node 匹配到的真实 ID，调用方在事务关闭后用它
          删除 ChromaDB 中的对应向量，避免残留。
        其他 change_type 均返回 (None, None)。
    """
    if record.status not in _ACCEPTED_STATUSES:
        return None, None

    payload = record.payload_edited or record.payload

    if record.change_type == "create_node":
        new_id = _apply_create_node(db, record, payload, pending_id_map or {})
        if pending_id_map is not None and record.pending_id:
            pending_id_map[record.pending_id] = new_id
        return new_id, None

    if record.change_type == "create_edge":
        _apply_create_edge(db, record, payload, pending_id_map or {})
        return None, None

    if record.change_type == "update_node":
        return _apply_update_node(db, record, payload), None

    if record.change_type == "delete_node":
        return None, _apply_delete_node(db, record)

    if record.change_type == "delete_edge":
        _apply_delete_edge(db, record, payload)
        return None, None

    return None, None


def _payload_anchor_node_id(payload: dict[str, Any]) -> str | None:
    """读取可选布局锚点字段，兼容 snake/camel case。"""
    raw = (
        payload.get("anchor_node_id")
        or payload.get("anchorNodeId")
        or payload.get("related_node_id")
        or payload.get("relatedNodeId")
    )
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _valid_project_node_id(db: Session, project_id: str, raw_id: str | None) -> str | None:
    """校验节点 ID 属于目标项目，返回规范 ID 或 None。"""
    if not raw_id:
        return None
    node = db.get(NodeORM, raw_id)
    if node is None or node.project_id != project_id:
        return None
    return node.id


def _resolve_layout_anchor_id(
    db: Session,
    record: AgentStagingORM,
    payload: dict[str, Any],
    pending_id_map: dict[str, str],
) -> str | None:
    """优先把新节点放在相关节点旁边，而不是让 LLM 输出绝对坐标。"""
    explicit_anchor = _valid_project_node_id(
        db,
        record.project_id,
        _payload_anchor_node_id(payload),
    )
    if explicit_anchor:
        return explicit_anchor

    if not record.pending_id or not record.batch_id:
        return None

    siblings = (
        db.query(AgentStagingORM)
        .filter(
            AgentStagingORM.batch_id == record.batch_id,
            AgentStagingORM.change_type == "create_edge",
        )
        .order_by(AgentStagingORM.order_in_batch)
        .all()
    )
    for sibling in siblings:
        edge_payload = sibling.payload_edited or sibling.payload or {}
        source = edge_payload.get("source")
        target = edge_payload.get("target")
        if source == record.pending_id:
            other = target
        elif target == record.pending_id:
            other = source
        else:
            continue

        other_id = str(other).strip() if other is not None else None
        if other_id in pending_id_map:
            return pending_id_map[other_id]
        existing = _valid_project_node_id(db, record.project_id, other_id)
        if existing:
            return existing

    return None


def _apply_create_node(
    db: Session,
    record: AgentStagingORM,
    payload: dict[str, Any],
    pending_id_map: dict[str, str],
) -> str:
    """将 staging.payload 转换成新节点。

    将生成的 node_id 写回 record.target_id，使之后“单条接受 create_edge”时可以从
    DB 查到 pending_id -> real node_id（跨 HTTP 请求复用映射）。按 create_node
    语义 target_id 原本为空，因此复用该字段不会破坏含义。
    """
    node_id = uuid.uuid4().hex

    title = str(payload.get("title") or "AI 建议节点")
    content = str(payload.get("content") or "")
    node_type = str(payload.get("node_type") or "character")
    graph_id = _resolve_graph_id(db, record.project_id, node_type)
    position = find_free_node_position(
        db,
        project_id=record.project_id,
        graph_id=graph_id,
        anchor_node_id=_resolve_layout_anchor_id(db, record, payload, pending_id_map),
    )
    parent_id = None
    sort_order = _payload_sort_order(payload)
    if node_type == "worldbuilding":
        parent_id = _validate_world_parent(
            db,
            record.project_id,
            _resolve_world_parent_id(payload, pending_id_map),
        )
        if sort_order is None:
            sort_order = _next_world_sort_order(db, record.project_id, parent_id)

    db.add(
        NodeORM(
            id=node_id,
            project_id=record.project_id,
            graph_id=graph_id,
            node_type=node_type,
            title=title,
            content=content,
            meta=api_meta_to_db(
                "AI 建议",
                ["AI 建议"],
                "synced",
                parent_id=parent_id,
                sort_order=sort_order,
            ),
            position_x=position.x,
            position_y=position.y,
            sort_order=9999,
        )
    )
    record.target_id = node_id
    db.flush()
    return node_id


def _resolve_endpoint(
    db: Session,
    project_id: str,
    raw_id: str | None,
    pending_id_map: dict[str, str],
) -> str | None:
    """将 payload 中的 source / target 转换成画布上的真实 node_id。

    优先匹配同批次新建节点的 pending_id；否则按真实 ID 查找 NodeORM 并校验项目归属。
    任一步失败都返回 None，由调用方决定如何降级（本模块选择静默跳过）。
    """
    if not raw_id:
        return None

    if raw_id in pending_id_map:
        raw_id = pending_id_map[raw_id]

    node = db.get(NodeORM, raw_id)
    if node is None or node.project_id != project_id:
        return None
    return node.id


def _apply_create_edge(
    db: Session,
    record: AgentStagingORM,
    payload: dict[str, Any],
    pending_id_map: dict[str, str],
) -> None:
    """将 staging.payload 转换成新边；端点解析失败时记录 warning 并跳过。"""
    src_raw = payload.get("source")
    tgt_raw = payload.get("target")
    source = _resolve_endpoint(db, record.project_id, src_raw, pending_id_map)
    target = _resolve_endpoint(db, record.project_id, tgt_raw, pending_id_map)

    if source is None or target is None:
        logger.warning(
            "create_edge skipped: staging=%s project=%s source=%r->%r target=%r->%r",
            record.id, record.project_id, src_raw, source, tgt_raw, target,
        )
        return

    src_node = db.get(NodeORM, source)
    tgt_node = db.get(NodeORM, target)
    if src_node.node_type != "plot" or tgt_node.node_type != "plot":
        logger.info(
            "create_edge skipped: non-plot endpoint staging=%s src=%s tgt=%s",
            record.id, src_node.node_type, tgt_node.node_type,
        )
        return

    relation_type = str(payload.get("relation_type") or "relates_to")
    label = str(payload.get("label") or relation_type)

    db.add(
        EdgeORM(
            id=uuid.uuid4().hex,
            project_id=record.project_id,
            source=source,
            target=target,
            label=label,
            relation_type=relation_type,
            edge_type=str(payload.get("edge_type") or "smoothstep"),
            sort_order=9999,
        )
    )
    db.flush()

_UPDATABLE_NODE_FIELDS = {"title", "content", "node_type"}


def _apply_update_node(
    db: Session,
    record: AgentStagingORM,
    payload: dict[str, Any],
) -> str | None:
    """将 staging.payload 合并到已有节点；目标节点不存在或越界时静默跳过。

    LLM 常用 update_node 补全已有节点设定；payload 只能覆盖白名单字段。世界观节点额外
    允许 parent_id / sort_order，以便 agent 把笔记放入树状层级；坐标仍由前端管理。
    """
    target_id = record.target_id
    if not target_id:
        return None

    node = db.get(NodeORM, target_id)
    if node is None or node.project_id != record.project_id:
        return None

    for field in _UPDATABLE_NODE_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        value = str(payload[field])
        setattr(node, field, value)
        if field == "node_type":
            node.graph_id = _resolve_graph_id(db, record.project_id, value)

    if node.node_type == "worldbuilding":
        parent_changed = _payload_has_parent(payload)
        sort_changed = "sort_order" in payload or "sortOrder" in payload
        if parent_changed or sort_changed:
            current_parent = db_parent_id_to_api(node.meta)
            next_parent = (
                _validate_world_parent(
                    db,
                    record.project_id,
                    _payload_parent_id(payload),
                    exclude_node_id=node.id,
                )
                if parent_changed
                else current_parent
            )
            if _world_parent_would_cycle(db, record.project_id, node.id, next_parent):
                next_parent = current_parent
            next_order = _payload_sort_order(payload)
            if next_order is None:
                next_order = (
                    _next_world_sort_order(db, record.project_id, next_parent)
                    if parent_changed
                    else db_sort_order_to_api(node.meta)
                )
            _set_world_hierarchy_meta(
                node,
                parent_id=next_parent,
                sort_order=next_order,
            )

    db.flush()
    return target_id


def _apply_delete_node(db: Session, record: AgentStagingORM) -> str | None:
    """删除节点；返回用于同步 ChromaDB 的 deleted node_id，失败或越界时返回 None。

    DB 已配置 ondelete=CASCADE + PRAGMA foreign_keys=ON，因此边会自动级联删除；
    这里手动删边是额外保险，防止环境忘记启用 PRAGMA，保证即使没有外键也不会在
    画布上留下指向已删除节点的孤儿边。
    """
    target_id = record.target_id
    if not target_id:
        logger.warning("delete_node skipped: staging=%s has no target_id", record.id)
        return None

    node = db.get(NodeORM, target_id)
    if node is None or node.project_id != record.project_id:
        logger.warning(
            "delete_node skipped: staging=%s node %s is not in project %s",
            record.id, target_id, record.project_id,
        )
        return None

    db.query(EdgeORM).filter(
        EdgeORM.project_id == record.project_id,
        (EdgeORM.source == target_id) | (EdgeORM.target == target_id),
    ).delete(synchronize_session=False)
    db.delete(node)
    db.flush()
    return target_id


def _apply_delete_edge(
    db: Session,
    record: AgentStagingORM,
    payload: dict[str, Any],
) -> None:
    """删除单条边。

    优先使用 record.target_id 精确查找（前端单条接受暂存项时由流程写入）；兜底策略是
    按 payload.(source, target, relation_type) 匹配项目中的第一条边。没有匹配项时
    静默跳过，避免 LLM 捏造不存在的 edge_id 导致 500。
    """
    edge = None
    if record.target_id:
        edge = db.get(EdgeORM, record.target_id)
        if edge is not None and edge.project_id != record.project_id:
            edge = None

    if edge is None:
        source = payload.get("source")
        target = payload.get("target")
        if source and target:
            query = db.query(EdgeORM).filter(
                EdgeORM.project_id == record.project_id,
                EdgeORM.source == source,
                EdgeORM.target == target,
            )
            relation = payload.get("relation_type")
            if relation:
                query = query.filter(EdgeORM.relation_type == relation)
            edge = query.first()

    if edge is None:
        logger.warning(
            "delete_edge skipped: staging=%s could not locate target edge target_id=%r payload=%s",
            record.id, record.target_id, payload,
        )
        return

    db.delete(edge)
    db.flush()
