"""Deterministic canvas placement helpers.

The LLM decides what to create; application code owns coordinates.  These
helpers place newly-created nodes near a useful anchor while avoiding overlap
with the existing nodes in the same subgraph.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import NodeORM


NODE_WIDTH = 260.0
NODE_HEIGHT = 150.0
NODE_GAP_X = 90.0
NODE_GAP_Y = 70.0
STEP_X = NODE_WIDTH + NODE_GAP_X
STEP_Y = NODE_HEIGHT + NODE_GAP_Y
DEFAULT_X = 120.0
DEFAULT_Y = 120.0
MAX_COLUMNS = 10
MAX_ROW_RADIUS = 10


@dataclass(frozen=True)
class CanvasPosition:
    x: float
    y: float


def _row_offsets(radius: int) -> list[int]:
    return [0, *range(1, radius + 1), *range(-1, -radius - 1, -1)]


def _overlaps(candidate: CanvasPosition, node: NodeORM) -> bool:
    return (
        candidate.x < node.position_x + NODE_WIDTH + NODE_GAP_X
        and candidate.x + NODE_WIDTH + NODE_GAP_X > node.position_x
        and candidate.y < node.position_y + NODE_HEIGHT + NODE_GAP_Y
        and candidate.y + NODE_HEIGHT + NODE_GAP_Y > node.position_y
    )


def _is_free(candidate: CanvasPosition, nodes: list[NodeORM]) -> bool:
    return all(not _overlaps(candidate, node) for node in nodes)


def _nodes_for_layout(
    db: Session,
    *,
    project_id: str,
    graph_id: str | None,
) -> list[NodeORM]:
    statement = select(NodeORM).where(NodeORM.project_id == project_id)
    if graph_id is None:
        statement = statement.where(NodeORM.graph_id.is_(None))
    else:
        statement = statement.where(NodeORM.graph_id == graph_id)
    return list(db.scalars(statement).all())


def _base_position(nodes: list[NodeORM], anchor: NodeORM | None) -> CanvasPosition:
    if anchor is not None:
        return CanvasPosition(anchor.position_x + STEP_X, anchor.position_y)

    if not nodes:
        return CanvasPosition(DEFAULT_X, DEFAULT_Y)

    rightmost = max(nodes, key=lambda node: (node.position_x, -node.position_y))
    return CanvasPosition(rightmost.position_x + STEP_X, rightmost.position_y)


def find_free_node_position(
    db: Session,
    *,
    project_id: str,
    graph_id: str | None,
    anchor_node_id: str | None = None,
) -> CanvasPosition:
    """Return a non-overlapping position in the target subgraph.

    Args:
        db: Current SQLAlchemy session.
        project_id: Project boundary.
        graph_id: Subgraph boundary; nodes in other subgraphs are ignored.
        anchor_node_id: Optional node to place beside.

    Returns:
        Top-left canvas coordinates for the new node.
    """
    nodes = _nodes_for_layout(db, project_id=project_id, graph_id=graph_id)
    anchor = (
        next((node for node in nodes if node.id == anchor_node_id), None)
        if anchor_node_id
        else None
    )
    base = _base_position(nodes, anchor)
    row_offsets = _row_offsets(MAX_ROW_RADIUS)

    for column in range(MAX_COLUMNS):
        for row_offset in row_offsets:
            candidate = CanvasPosition(
                x=base.x + column * STEP_X,
                y=base.y + row_offset * STEP_Y,
            )
            if _is_free(candidate, nodes):
                return candidate

    fallback_index = len(nodes)
    return CanvasPosition(
        x=base.x + (fallback_index % MAX_COLUMNS) * STEP_X,
        y=base.y + (MAX_ROW_RADIUS + fallback_index // MAX_COLUMNS + 1) * STEP_Y,
    )
