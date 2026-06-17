"""节点自定义字段服务（first_revision 决策 2）。

角色卡的“自定义字段”（例如阵营 / 年龄 / 身高）存储在 ``NodeORM.meta`` JSON 的
``fields`` 键下，不新增表，也不污染已有的 text / tags / status。读写后复用既有
``safe_sync_node_index``，保持 RAG 索引一致。
"""

from fastapi import HTTPException

from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.indexing.sync import build_node_fingerprint, safe_sync_node_index
from app.schemas import NodeFieldsPayload
from app.services.graph_mappers import db_fields_to_api, merge_fields_into_meta
from app.services.graph_repository import read_project_node, require_project


def get_node_fields(project_id: str, node_id: str) -> NodeFieldsPayload:
    """读取节点自定义字段。"""
    with SessionLocal() as session:
        require_project(session, project_id)
        node = session.get(NodeORM, node_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="未找到节点")
        return NodeFieldsPayload(node_id=node_id, fields=db_fields_to_api(node.meta))


def set_node_fields(project_id: str, node_id: str, fields: dict[str, str]) -> NodeFieldsPayload:
    """整体替换节点自定义字段，并在提交后同步索引。"""
    with SessionLocal.begin() as session:
        require_project(session, project_id)
        node = session.get(NodeORM, node_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="未找到节点")

        old_fingerprint = build_node_fingerprint(node)
        node.meta = merge_fields_into_meta(node.meta, fields)
        saved = db_fields_to_api(node.meta)

    latest = read_project_node(project_id, node_id)
    if latest is not None:
        safe_sync_node_index(latest, old_fingerprint)

    return NodeFieldsPayload(node_id=node_id, fields=saved)
