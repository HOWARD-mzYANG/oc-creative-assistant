"""图谱数据库操作辅助函数。

本模块是服务层与 ORM 之间的持久化边界，负责读写数据库中的项目、节点和边。
它不处理 HTTP 请求，也不触发 ChromaDB 同步；外部副作用由服务编排层在事务提交后执行。
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import EdgeORM, GraphORM, NodeORM, ProjectORM
from app.schemas import EdgePayload, NodePayload
from app.services.graph_mappers import edge_to_orm, node_to_orm
from app.services.graph_validation import validate_edges_against_payload_nodes


_SECTION_BY_NODE_TYPE: dict[str, str] = {
    "character": "character",
    "worldbuilding": "world",
    "plot": "plot",
}
_DEFAULT_SECTION = "plot"
_GRAPH_ATTR_BY_SECTION = {
    "plot": "plot_graph_id",
    "character": "character_graph_id",
    "world": "world_graph_id",
}


def resolve_graph_id_for_node_type(
    project: ProjectORM | None,
    node_type: str | None,
) -> str | None:
    """按节点类型找到项目下对应子图 ID；旧项目缺少子图时返回 None。"""
    if project is None:
        return None
    section = _SECTION_BY_NODE_TYPE.get(node_type or "", _DEFAULT_SECTION)
    attr = _GRAPH_ATTR_BY_SECTION[section]
    value = getattr(project, attr, None)
    return value if isinstance(value, str) and value else None


def _graph_id_for_project_node(project: ProjectORM | None, node: NodePayload) -> str | None:
    """按节点 payload 找到项目下对应子图 ID。"""
    return resolve_graph_id_for_node_type(project, node.nodeType or node.type)


def require_project(session: Session, project_id: str) -> ProjectORM:
    """读取项目并确认存在。

    Args:
        session: 当前数据库 session。
        project_id: 项目 ID。

    Returns:
        匹配的项目 ORM 对象。

    Raises:
        HTTPException: 项目不存在时抛出。
    """
    project = session.get(ProjectORM, project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="未找到项目")

    return project


def read_ordered_nodes(session: Session, project_id: str) -> list[NodeORM]:
    """按画布保存顺序读取项目节点。

    Args:
        session: 当前数据库 session。
        project_id: 项目 ID。

    Returns:
        当前项目的节点 ORM 对象列表。
    """
    return session.scalars(
        select(NodeORM)
        .where(NodeORM.project_id == project_id)
        .order_by(NodeORM.sort_order, NodeORM.created_at)
    ).all()


def read_ordered_edges(session: Session, project_id: str) -> list[EdgeORM]:
    """按画布保存顺序读取项目边。

    Args:
        session: 当前数据库 session。
        project_id: 项目 ID。

    Returns:
        当前项目的边 ORM 对象列表。
    """
    return session.scalars(
        select(EdgeORM)
        .where(EdgeORM.project_id == project_id)
        .order_by(EdgeORM.sort_order, EdgeORM.created_at)
    ).all()


def read_project_nodes(project_id: str) -> list[NodeORM]:
    """读取项目节点快照。

    该函数会打开独立 session，让服务层能在 SQLite 事务之外比较向量索引指纹。

    Args:
        project_id: 项目 ID。

    Returns:
        当前项目的节点 ORM 对象列表。
    """
    with SessionLocal() as session:
        return read_ordered_nodes(session, project_id)


def read_project_node(project_id: str, node_id: str) -> NodeORM | None:
    """读取单个节点快照。

    该函数会在事务提交后重新读取节点，确保索引同步使用的是已持久化到 SQLite 的状态。

    Args:
        project_id: 项目 ID。
        node_id: 节点 ID。

    Returns:
        匹配的节点 ORM；节点不存在或不属于该项目时返回 None。
    """
    with SessionLocal() as session:
        node = session.get(NodeORM, node_id)

        if node is None or node.project_id != project_id:
            return None

        return node


def replace_graph(
    session: Session,
    project_id: str,
    nodes: list[NodePayload],
    edges: list[EdgePayload],
) -> None:
    """在当前事务内整体替换项目图谱。

    保存策略基于完整快照：先校验边端点只引用本次提交中的节点，再删除旧边和旧节点，最后按
    提交顺序写入新节点和新边。

    Args:
        session: 当前数据库事务 session。
        project_id: 项目 ID。
        nodes: 本次要保存的完整节点列表。
        edges: 本次要保存的完整边列表。

    Raises:
        HTTPException: 边引用当前图谱之外节点时抛出。
    """
    validate_edges_against_payload_nodes(nodes, edges)
    project = session.get(ProjectORM, project_id)
    # SQLite 外键约束会阻止删除仍被边引用的节点，因此整体替换时必须先删边。
    session.query(EdgeORM).filter(EdgeORM.project_id == project_id).delete(synchronize_session=False)
    session.query(NodeORM).filter(NodeORM.project_id == project_id).delete(synchronize_session=False)

    for index, node in enumerate(nodes):
        session.add(
            node_to_orm(
                project_id,
                node,
                index,
                graph_id=_graph_id_for_project_node(project, node),
            )
        )

    for index, edge in enumerate(edges):
        session.add(edge_to_orm(project_id, edge, index))


# --- 子图级操作（first_revision 决策 1） ---


def require_graph(session: Session, graph_id: str) -> GraphORM:
    """读取子图并确认存在。

    Raises:
        HTTPException: 子图不存在时抛 404。
    """
    graph = session.get(GraphORM, graph_id)

    if graph is None:
        raise HTTPException(status_code=404, detail="未找到图谱")

    return graph


def read_ordered_nodes_by_graph(session: Session, graph_id: str) -> list[NodeORM]:
    """按画布保存顺序读取子图节点。"""
    return session.scalars(
        select(NodeORM)
        .where(NodeORM.graph_id == graph_id)
        .order_by(NodeORM.sort_order, NodeORM.created_at)
    ).all()


def read_intra_graph_edges(session: Session, graph_id: str) -> list[EdgeORM]:
    """读取两个端点都落在该子图内的边。

    第 1 阶段只处理子图内部边；跨子图边在第 6 阶段引入。
    """
    node_ids = {
        node_id
        for (node_id,) in session.execute(
            select(NodeORM.id).where(NodeORM.graph_id == graph_id)
        ).all()
    }
    if not node_ids:
        return []

    return session.scalars(
        select(EdgeORM)
        .where(EdgeORM.source.in_(node_ids), EdgeORM.target.in_(node_ids))
        .order_by(EdgeORM.sort_order, EdgeORM.created_at)
    ).all()


def read_graph_nodes(graph_id: str) -> list[NodeORM]:
    """在独立 session 中读取子图节点快照，用于在事务外比较索引指纹。"""
    with SessionLocal() as session:
        return read_ordered_nodes_by_graph(session, graph_id)


def replace_subgraph(
    session: Session,
    graph: GraphORM,
    nodes: list[NodePayload],
    edges: list[EdgePayload],
) -> None:
    """整体替换子图的节点和内部边。

    结构上与 ``replace_graph`` 相同，但范围缩小到单个子图：只删除/写入属于该子图的节点，以及
    两个端点都位于该子图内的边，不影响项目下其他子图。
    """
    validate_edges_against_payload_nodes(nodes, edges)

    old_node_ids = {
        node_id
        for (node_id,) in session.execute(
            select(NodeORM.id).where(NodeORM.graph_id == graph.id)
        ).all()
    }
    # 先删除子图内部边（外键约束会阻止删除仍被边引用的节点），再删除节点。
    if old_node_ids:
        session.query(EdgeORM).filter(
            EdgeORM.source.in_(old_node_ids), EdgeORM.target.in_(old_node_ids)
        ).delete(synchronize_session=False)
    session.query(NodeORM).filter(NodeORM.graph_id == graph.id).delete(
        synchronize_session=False
    )

    for index, node in enumerate(nodes):
        session.add(node_to_orm(graph.project_id, node, index, graph_id=graph.id))

    for index, edge in enumerate(edges):
        session.add(edge_to_orm(graph.project_id, edge, index))
