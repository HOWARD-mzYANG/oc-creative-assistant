"""RAG 检索与上下文合并。

本模块负责从画布图中提取一跳关系上下文，通过向量索引找到语义相关节点，最后合并并去重成前端和
prompt 都可使用的上下文列表。
"""

from __future__ import annotations

from app.db.models import EdgeORM, NodeORM
from app.indexing.config import DEFAULT_RELATION_LABEL, DEFAULT_RELATION_TYPE
from app.indexing.document_loader import node_to_vector_item
from app.indexing.vector_store import (
    embed_query,
    get_all_chroma_collections,
    get_chroma_collection_for_node,
    query_collection,
)
from app.schemas import RagGraphContextItem, RagMergedContextItem, RagVectorContextItem


def build_graph_context(
    node_id: str,
    nodes: list[NodeORM],
    edges: list[EdgeORM],
) -> list[RagGraphContextItem]:
    """构建一跳图关系上下文。

    画布边是用户显式建立的创作关系，因此优先级高于语义相似度。

    参数：
        node_id: 当前节点 ID。
        nodes: 当前项目的完整节点快照。
        edges: 当前项目的完整边快照。

    返回：
        与当前节点直接相连的图关系上下文。
    """
    node_by_id = {node.id: node for node in nodes}
    context: list[RagGraphContextItem] = []

    for edge in edges:
        if edge.source == node_id:
            neighbor = node_by_id.get(edge.target)
            direction = "outgoing"
        elif edge.target == node_id:
            neighbor = node_by_id.get(edge.source)
            direction = "incoming"
        else:
            continue

        if neighbor is None:
            # 保存层已经校验端点；这里防御性跳过脏数据，避免整个 RAG 端点失败。
            continue

        context.append(
            RagGraphContextItem(
                id=neighbor.id,
                type=neighbor.node_type,
                title=neighbor.title,
                content=neighbor.content,
                relation_label=edge.label or DEFAULT_RELATION_LABEL,
                relation_type=edge.relation_type or DEFAULT_RELATION_TYPE,
                direction=direction,
            )
        )

    return context


def build_project_vector_context(
    project_id: str,
    nodes: list[NodeORM],
    query: str,
    top_k: int,
    node_type: str | None = None,
) -> tuple[list[RagVectorContextItem], str, str | None]:
    """构建项目级向量检索上下文。

    参数：
        project_id: 当前项目 ID。
        nodes: 当前项目的完整节点快照。
        query: 用户输入的检索问题。
        top_k: 最多返回的向量上下文条数。
        node_type: 可选节点类型过滤器。

    返回：
        相似节点列表、实际使用的向量库标识，以及可选错误信息。
    """
    candidate_nodes = [node for node in nodes if node_type is None or node.node_type == node_type]

    if not query.strip() or not candidate_nodes:
        return [], "chroma", None

    try:
        return _query_project_chroma_context(project_id, candidate_nodes, query, top_k, node_type)
    except Exception as error:  # noqa: BLE001
        import traceback
        print(f"[retrieval] chroma_unavailable: {error!r}", flush=True)
        traceback.print_exc()
        return [], "chroma_unavailable", str(error)


def _query_project_chroma_context(
    project_id: str,
    nodes: list[NodeORM],
    query: str,
    top_k: int,
    node_type: str | None = None,
) -> tuple[list[RagVectorContextItem], str, str | None]:
    """跨集合执行项目级 Lore Memory 检索。

    指定 node_type 时只查询对应集合；否则查询三个集合，并按分数取 top_k。多集合检索时会复用同一个
    query embedding，避免每个集合都调用一次 embedding API；这是 RAG 路径上最容易放大 embedding
    调用次数的地方。
    """
    print(
        f"[debug-retrieval] node_type={node_type!r} query={query[:30]!r} "
        f"nodes_count={len(nodes)} top_k={top_k}",
        flush=True,
    )
    node_by_id = {node.id: node for node in nodes}

    if node_type is not None:
        print(f"[debug-retrieval] -> SINGLE collection branch (node_type={node_type})", flush=True)
        collection = get_chroma_collection_for_node(node_type)
        ids, metadatas, distances = query_collection(collection, project_id, query, top_k)
        return _hits_to_items(ids, metadatas, distances, node_by_id, top_k), "chroma", None

    print("[debug-retrieval] -> MULTI collection branch (node_type=None)", flush=True)
    query_embedding = embed_query(query)

    all_items: list[RagVectorContextItem] = []
    for collection in get_all_chroma_collections().values():
        print(f"[debug-retrieval]    iter collection.name={collection.name!r}", flush=True)
        ids, metadatas, distances = query_collection(
            collection, project_id, query, top_k, query_embedding=query_embedding,
        )
        all_items.extend(_hits_to_items(ids, metadatas, distances, node_by_id, top_k))

    all_items.sort(key=lambda item: item.score, reverse=True)
    return all_items[:top_k], "chroma", None


def _hits_to_items(
    ids: list[str],
    metadatas: list[dict],
    distances: list[float],
    node_by_id: dict[str, NodeORM],
    top_k: int,
) -> list[RagVectorContextItem]:
    """将 ChromaDB 命中转换为 RagVectorContextItem，并防御性处理过期 metadata。"""
    items: list[RagVectorContextItem] = []

    for _, metadata, distance in zip(ids, metadatas, distances, strict=False):
        target_id = metadata.get("node_id") if isinstance(metadata, dict) else None

        if not isinstance(target_id, str):
            continue

        target_node = node_by_id.get(target_id)
        if target_node is None:
            continue

        items.append(node_to_vector_item(target_node, score=max(0.0, 1.0 - float(distance))))

        if len(items) >= top_k:
            break

    return items

def merge_context(
    graph_context: list[RagGraphContextItem],
    vector_context: list[RagVectorContextItem],
) -> list[RagMergedContextItem]:
    """合并图关系上下文和向量上下文。

    同一个节点可能同时来自图关系和向量检索，因此需要去重，避免重复注入 prompt。
    """
    merged: dict[str, RagMergedContextItem] = {}

    for item in graph_context:
        merged[item.id] = RagMergedContextItem(
            id=item.id,
            source="graph",
            type=item.type,
            title=item.title,
            content=item.content,
        )

    for item in vector_context:
        if item.id in merged:
            existing_item = merged[item.id]
            merged[item.id] = RagMergedContextItem(
                id=existing_item.id,
                source="both",
                type=existing_item.type,
                title=existing_item.title,
                content=existing_item.content,
            )
            continue

        merged[item.id] = RagMergedContextItem(
            id=item.id,
            source="vector",
            type=item.type,
            title=item.title,
            content=item.content,
        )

    return list(merged.values())
