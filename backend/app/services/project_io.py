"""项目导入/导出：无损 .oc 快照（故事 + 角色 + 世界观）。"""
from __future__ import annotations

import uuid

from app.db.database import SessionLocal
from app.db.models import EdgeORM, NodeORM, ProjectORM
from app.indexing.sync import safe_sync_node_index
from app.services.canvas_apply import _resolve_graph_id

OC_FORMAT_VERSION = 1


def export_project_oc(project_id: str) -> dict:
    """导出三个子图的无损快照，用于备份 / 迁移。"""
    from app.services.graph_repository import read_ordered_edges, read_ordered_nodes

    with SessionLocal() as db:
        project = db.get(ProjectORM, project_id)
        if project is None:
            raise ValueError("未找到项目")
        nodes = read_ordered_nodes(db, project_id)
        edges = read_ordered_edges(db, project_id)
        return {
            "format": "oc",
            "version": OC_FORMAT_VERSION,
            "project": {"name": project.name, "description": project.description},
            "nodes": [
                {
                    "id": n.id,
                    "node_type": n.node_type,
                    "title": n.title,
                    "content": n.content,
                    "meta": n.meta,
                    "position_x": n.position_x,
                    "position_y": n.position_y,
                    "sort_order": n.sort_order,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "label": e.label,
                    "relation_type": e.relation_type,
                    "edge_type": e.edge_type,
                    "sort_order": e.sort_order,
                }
                for e in edges
            ],
        }


def import_project_oc(data: dict) -> str:
    """把 .oc 快照恢复成一个新项目，并重新生成 ID 以避免冲突。

    返回新的 project_id。端点缺失的边会被跳过。
    """
    from app.schemas import ProjectCreateRequest
    from app.services.project_service import create_project

    if not isinstance(data, dict) or data.get("format") != "oc":
        raise ValueError("不是有效的 .oc 文件")

    meta = data.get("project") or {}
    detail = create_project(
        ProjectCreateRequest(
            name=str(meta.get("name") or "导入项目"),
            description=str(meta.get("description") or ""),
        )
    )
    project_id = detail.id

    id_map: dict[str, str] = {}
    new_node_ids: list[str] = []

    with SessionLocal.begin() as db:
        for n in data.get("nodes", []):
            new_id = uuid.uuid4().hex
            if n.get("id"):
                id_map[n["id"]] = new_id
            node_type = str(n.get("node_type") or "character")
            db.add(
                NodeORM(
                    id=new_id,
                    project_id=project_id,
                    graph_id=_resolve_graph_id(db, project_id, node_type),
                    node_type=node_type,
                    title=str(n.get("title") or "未命名"),
                    content=str(n.get("content") or ""),
                    meta=n.get("meta") or {"tags": [], "status": "synced"},
                    position_x=float(n.get("position_x") or 0.0),
                    position_y=float(n.get("position_y") or 0.0),
                    sort_order=int(n.get("sort_order") or 0),
                )
            )
            new_node_ids.append(new_id)

        for e in data.get("edges", []):
            source = id_map.get(e.get("source"))
            target = id_map.get(e.get("target"))
            if not (source and target):
                continue
            db.add(
                EdgeORM(
                    id=uuid.uuid4().hex,
                    project_id=project_id,
                    source=source,
                    target=target,
                    label=str(e.get("label") or ""),
                    relation_type=str(e.get("relation_type") or "relates_to"),
                    edge_type=str(e.get("edge_type") or "smoothstep"),
                    sort_order=int(e.get("sort_order") or 0),
                )
            )

    with SessionLocal() as db:
        for node_id in new_node_ids:
            node = db.get(NodeORM, node_id)
            if node is not None:
                safe_sync_node_index(node)

    return project_id
