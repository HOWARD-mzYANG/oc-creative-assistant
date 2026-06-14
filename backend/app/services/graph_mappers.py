"""Graph DTO <-> ORM 转换。

本模块是服务层的数据映射边界，负责在 API payload 与 SQLAlchemy ORM 之间转换，
并维护节点 meta JSON 的兼容规则。它不访问数据库，也不触发索引同步。
"""

from __future__ import annotations

from typing import Any

from app.db.models import EdgeORM, NodeORM, ProjectORM
from app.indexing.config import DEFAULT_NODE_STATUS
from app.schemas import (
    EdgePayload,
    EdgeWaypointPayload,
    NodePayload,
    PositionPayload,
    ProjectPayload,
)


META_TEXT_KEY = "text"
META_TAGS_KEY = "tags"
META_STATUS_KEY = "status"
# first_revision 决策 2：保留键，用于把角色卡的“自由字段”存入 node.meta JSON，
# 同时不污染既有 text / tags / status。
META_FIELDS_KEY = "fields"
META_PARENT_ID_KEY = "parentId"
META_SORT_ORDER_KEY = "sortOrder"


def db_fields_to_api(meta: Any) -> dict[str, str]:
    """从数据库 meta 读取自由字段（key -> value，均为字符串）。"""
    if isinstance(meta, dict):
        fields = meta.get(META_FIELDS_KEY, {})
        if isinstance(fields, dict):
            return {str(k): str(v) for k, v in fields.items()}
    return {}


def merge_fields_into_meta(meta: Any, fields: dict[str, str]) -> dict[str, Any]:
    """把自由字段整体写回 meta JSON，同时保留其他保留键。"""
    stored_meta: dict[str, Any] = meta if isinstance(meta, dict) else {}
    next_meta = dict(stored_meta)
    next_meta[META_FIELDS_KEY] = {str(k): str(v) for k, v in fields.items()}
    return next_meta


def project_to_payload(project: ProjectORM) -> ProjectPayload:
    """将 project ORM 转换为 API payload。

    参数：
        project: 数据库中的项目记录。

    返回：
        前端接口使用的项目 DTO。
    """
    return ProjectPayload(id=project.id, name=project.name)


def node_to_payload(node: NodeORM) -> NodePayload:
    """将 node ORM 转换为 API payload。

    兼容旧版字符串 meta 与当前 JSON meta，确保前端仍能收到稳定的
    `meta`、`tags` 和 `status` 字段。

    参数：
        node: 数据库中的节点记录。

    返回：
        前端接口使用的节点 DTO。
    """
    return NodePayload(
        id=node.id,
        type=node.node_type,
        nodeType=node.node_type,
        title=node.title,
        content=node.content,
        meta=db_meta_to_api(node.meta),
        typeLabel=node.type_label,
        tags=db_tags_to_api(node.meta),
        status=db_status_to_api(node.meta),
        parentId=db_parent_id_to_api(node.meta),
        sortOrder=db_sort_order_to_api(node.meta),
        position=PositionPayload(x=node.position_x, y=node.position_y),
    )


def edge_to_payload(edge: EdgeORM) -> EdgePayload:
    """将 edge ORM 转换为 API payload。"""
    waypoint = (
        EdgeWaypointPayload.model_validate(edge.waypoint) if edge.waypoint else None
    )
    return EdgePayload(
        id=edge.id,
        source=edge.source,
        target=edge.target,
        label=edge.label or "related",
        relationType=edge.relation_type or "relates_to",
        sourceHandle=edge.source_handle,
        targetHandle=edge.target_handle,
        type=edge.edge_type,
        animated=edge.animated,
        waypoint=waypoint,
    )


def node_to_orm(
    project_id: str,
    node: NodePayload,
    sort_order: int,
    graph_id: str | None = None,
) -> NodeORM:
    """将 node payload 转换为 ORM。

    参数：
        project_id: 节点所属项目 ID。
        node: 前端提交的节点 DTO。
        sort_order: 节点在当前图快照中的顺序。
        graph_id: 节点所属子图；项目级保存时为 None，子图级保存时由调用方传入
            （first_revision 决策 1）。

    返回：
        可直接写入数据库的节点 ORM 对象。
    """
    return NodeORM(
        id=node.id,
        project_id=project_id,
        graph_id=graph_id,
        node_type=node.nodeType or node.type,
        title=node.title,
        content=node.content,
        meta=api_meta_to_db(
            node.meta,
            node.tags,
            node.status,
            parent_id=node.parentId,
            sort_order=node.sortOrder,
        ),
        type_label=node.typeLabel,
        position_x=node.position.x,
        position_y=node.position.y,
        sort_order=sort_order,
    )


def edge_to_orm(project_id: str, edge: EdgePayload, sort_order: int) -> EdgeORM:
    """将 edge payload 转换为 ORM。"""
    return EdgeORM(
        id=edge.id,
        project_id=project_id,
        source=edge.source,
        target=edge.target,
        label=edge.label or "related",
        source_handle=edge.sourceHandle,
        target_handle=edge.targetHandle,
        edge_type=edge.type,
        relation_type=edge.relationType,
        animated=edge.animated,
        waypoint=edge.waypoint.model_dump() if edge.waypoint else None,
        sort_order=sort_order,
    )


def api_meta_to_db(
    meta: str,
    tags: list[str] | None = None,
    status: str | None = None,
    existing_meta: Any | None = None,
    parent_id: str | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    """将 API meta 字段合并到数据库 JSON。

    API 仍保留字符串 `meta` 字段；数据库使用 JSON 一起存储正文、标签和同步状态，
    避免在当前 PoC 阶段扩展表结构。

    参数：
        meta: 前端提交的字符串 meta。
        tags: 可选标签列表；为 None 时保留现有标签，或写入默认空列表。
        status: 可选同步状态；为 None 时保留现有状态，或写入默认状态。
        existing_meta: 更新节点时数据库中已有的 meta。

    返回：
        可写入 NodeORM.meta 的 JSON dict。
    """
    stored_meta: dict[str, Any] = existing_meta if isinstance(existing_meta, dict) else {}
    next_meta = dict(stored_meta)

    if meta:
        next_meta[META_TEXT_KEY] = meta
    else:
        next_meta.pop(META_TEXT_KEY, None)

    if tags is not None:
        next_meta[META_TAGS_KEY] = [tag for tag in tags if isinstance(tag, str)]
    elif META_TAGS_KEY not in next_meta:
        next_meta[META_TAGS_KEY] = []

    if status is not None:
        next_meta[META_STATUS_KEY] = status
    elif META_STATUS_KEY not in next_meta:
        next_meta[META_STATUS_KEY] = DEFAULT_NODE_STATUS

    if parent_id:
        next_meta[META_PARENT_ID_KEY] = parent_id
    else:
        next_meta.pop(META_PARENT_ID_KEY, None)

    if sort_order is not None:
        next_meta[META_SORT_ORDER_KEY] = sort_order

    return next_meta


def db_meta_to_api(meta: Any) -> str:
    """从数据库 meta 中读取 API 字符串 meta。"""
    if isinstance(meta, dict):
        value = meta.get(META_TEXT_KEY, "")
        return value if isinstance(value, str) else ""

    if isinstance(meta, str):
        return meta

    return ""


def db_tags_to_api(meta: Any) -> list[str]:
    """从数据库 meta 中读取 API tags。"""
    if isinstance(meta, dict):
        tags = meta.get(META_TAGS_KEY, [])
        return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []

    return []


def db_status_to_api(meta: Any) -> str:
    """从数据库 meta 中读取 API status。"""
    if isinstance(meta, dict):
        status = meta.get(META_STATUS_KEY, DEFAULT_NODE_STATUS)
        return status if isinstance(status, str) else DEFAULT_NODE_STATUS

    return DEFAULT_NODE_STATUS


def db_parent_id_to_api(meta: Any) -> str | None:
    """从数据库 meta 中读取世界观文件夹父级 ID。"""
    if isinstance(meta, dict):
        parent_id = meta.get(META_PARENT_ID_KEY)
        return parent_id if isinstance(parent_id, str) and parent_id else None

    return None


def db_sort_order_to_api(meta: Any) -> int:
    """从数据库 meta 中读取世界观文件夹同级排序。"""
    if isinstance(meta, dict):
        sort_order = meta.get(META_SORT_ORDER_KEY, 0)
        return sort_order if isinstance(sort_order, int) else 0

    return 0
