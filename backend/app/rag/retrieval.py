"""RAG retrieval and context merging.

This module is responsible for extracting one-hop relation context from the canvas
graph, finding semantically related nodes via the vector index, and finally merging
and deduplicating them into a context list usable by the frontend and the prompt.
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
    """Build the one-hop graph relation context.

    Canvas edges are creative relations the user explicitly established, so they take
    priority over semantic similarity.

    参数：
        node_id: The current node ID.
        nodes: The full node snapshot of the current project.
        edges: The full edge snapshot of the current project.

    返回：
        The graph relation context directly connected to the current node.
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
            # The save layer already validates endpoints; here we defensively skip dirty data to avoid failing the whole RAG endpoint.
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
    """Build the project-level vector retrieval context.

    参数：
        project_id: The current project ID.
        nodes: The full node snapshot of the current project.
        query: The retrieval question entered by the user.
        top_k: The maximum number of vector context items to return.
        node_type: Optional node type filter.

    返回：
        The list of similar nodes, the identifier of the vector store actually used,
        and an optional error message.
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
    """Perform project-level Lore Memory retrieval across collections.

    When node_type is specified, only the corresponding collection is queried;
    otherwise all three collections are queried and the top_k are taken by score.
    With multiple collections, the same query embedding is reused to avoid calling
    the embedding API once per collection; this is the biggest amplification point
    for embedding calls on the RAG path.
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
    """Convert ChromaDB hits into RagVectorContextItem, defensively handling stale metadata."""
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
    """Merge the graph relation context and the vector context.

    The same node may come from both the graph relations and the vector retrieval,
    so deduplication is needed to avoid injecting it into the prompt twice.
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
