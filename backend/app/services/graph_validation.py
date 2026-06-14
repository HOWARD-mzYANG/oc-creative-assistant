"""Graph business validation rules.

This module is the service layer's business-rule boundary, responsible for
validating the project consistency of nodes and edges.
It does not write to the database, nor does it decide the HTTP routing structure.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import NodeORM
from app.schemas import EdgePayload, NodePayload


def validate_edges_against_payload_nodes(nodes: list[NodePayload], edges: list[EdgePayload]) -> None:
    """Validate that edges in a full graph snapshot only reference nodes from this submission.

    参数：
        nodes: The complete list of nodes submitted in this save.
        edges: The complete list of edges submitted in this save.

    抛出：
        HTTPException: Raised when any edge references a node outside the current
            graph.
    """
    node_ids = {node.id for node in nodes}
    invalid_edge = next(
        (edge for edge in edges if edge.source not in node_ids or edge.target not in node_ids),
        None,
    )

    if invalid_edge is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Edge {invalid_edge.id} references a node outside current graph",
        )


def validate_edge_endpoints_in_project(
    session: Session,
    project_id: str,
    source: str,
    target: str,
) -> None:
    """Validate that both endpoints of a single edge belong to the same project.

    参数：
        session: The current database session.
        project_id: The ID of the project the edge belongs to.
        source: The source node ID.
        target: The target node ID.

    抛出：
        HTTPException: Raised when an endpoint is missing or does not belong to the
            current project.
    """
    endpoint_count = session.scalar(
        select(func.count())
        .select_from(NodeORM)
        .where(
            NodeORM.project_id == project_id,
            NodeORM.id.in_([source, target]),
        )
    )

    if endpoint_count != 2:
        raise HTTPException(status_code=400, detail="Edge endpoints must belong to the same project")
