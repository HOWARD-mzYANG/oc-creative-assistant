"""Node custom fields service (first_revision decision 2).

A character card's "custom fields" (such as faction / age / height) are stored
under the ``fields`` key of the ``NodeORM.meta`` JSON, without adding new tables
or polluting the existing text / tags / status. After reads and writes, the
existing ``safe_sync_node_index`` is reused to keep the RAG index consistent.
"""

from fastapi import HTTPException

from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.indexing.sync import build_node_fingerprint, safe_sync_node_index
from app.schemas import NodeFieldsPayload
from app.services.graph_mappers import db_fields_to_api, merge_fields_into_meta
from app.services.graph_repository import read_project_node, require_project


def get_node_fields(project_id: str, node_id: str) -> NodeFieldsPayload:
    """读取 node's custom fields."""
    with SessionLocal() as session:
        require_project(session, project_id)
        node = session.get(NodeORM, node_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="Node not found")
        return NodeFieldsPayload(node_id=node_id, fields=db_fields_to_api(node.meta))


def set_node_fields(project_id: str, node_id: str, fields: dict[str, str]) -> NodeFieldsPayload:
    """Replace a node's custom fields as a whole, and sync the index after commit."""
    with SessionLocal.begin() as session:
        require_project(session, project_id)
        node = session.get(NodeORM, node_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="Node not found")

        old_fingerprint = build_node_fingerprint(node)
        node.meta = merge_fields_into_meta(node.meta, fields)
        saved = db_fields_to_api(node.meta)

    latest = read_project_node(project_id, node_id)
    if latest is not None:
        safe_sync_node_index(latest, old_fingerprint)

    return NodeFieldsPayload(node_id=node_id, fields=saved)
