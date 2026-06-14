"""ChromaDB 向量存储封装。

只负责 ChromaDB collection 初始化、项目隔离的 id/metadata 约定，以及节点文档的
upsert/delete/query。Embedding 计算和 provider 选择由
``app.indexing.embedding_provider`` 处理；索引同步时机由 ``app.indexing.sync`` 决定。
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.models import NodeORM
from app.indexing.config import (
    CHROMA_PATH,
    COLLECTION_BY_NODE_TYPE,
    DEFAULT_COLLECTION_NAME,
    INDEXING_DEBUG_LOG,
)
from app.indexing.document_loader import node_to_document
from app.indexing.embedding_provider import (
    embed_query,
    embedding_provider,
    get_embedding_signature,
)


logger = logging.getLogger(__name__)


def _log(message: str) -> None:
    """打印向量写入信息，使 PoC 阶段的真实执行路径可观察。"""
    if INDEXING_DEBUG_LOG:
        print(f"[vector-store] {message}", flush=True)


def build_chroma_id(project_id: str, node_id: str) -> str:
    """构建 ChromaDB 记录 ID。

    参数：
        project_id: 节点所属项目 ID。
        node_id: 节点 ID。

    返回：
        由项目和节点组成的稳定记录 ID，避免不同项目中的同名节点互相覆盖。
    """
    return f"{project_id}:{node_id}"


def _resolve_collection_name(node_type: str) -> str:
    """根据 node_type 路由到目标 collection 名称，未命中时回退到默认 collection。"""
    return COLLECTION_BY_NODE_TYPE.get(node_type, DEFAULT_COLLECTION_NAME)


def _all_collection_names() -> tuple[str, ...]:
    """返回所有需要管理的 collection 名称，包括默认 collection。"""
    return (*COLLECTION_BY_NODE_TYPE.values(), DEFAULT_COLLECTION_NAME)


def _build_chroma_client() -> Any:
    """初始化 ChromaDB PersistentClient。

    抛出：
        RuntimeError: 未安装 ChromaDB 时抛出。
    """
    try:
        import chromadb
    except ImportError as error:
        raise RuntimeError("未安装 ChromaDB，无法写入或查询向量索引。") from error

    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


_chroma_client_singleton: Any | None = None


def _get_chroma_client() -> Any:
    """进程级单例。
    """
    global _chroma_client_singleton
    if _chroma_client_singleton is None:
        _chroma_client_singleton = _build_chroma_client()
    return _chroma_client_singleton


def get_chroma_collection_by_name(name: str) -> Any:
    """按名称获取 collection；不存在时自动以 cosine 距离创建。"""
    client = _get_chroma_client()
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def get_chroma_collection_for_node(node_type: str) -> Any:
    """按 node_type 路由到对应 collection；调用方无需关心命名。"""
    return get_chroma_collection_by_name(_resolve_collection_name(node_type))


def get_all_chroma_collections() -> dict[str, Any]:
    """返回所有 collection，用于跨 collection 扫描（同步状态读取 / 完整 Lore Memory 检索）。"""
    return {name: get_chroma_collection_by_name(name) for name in _all_collection_names()}


def upsert_node(node: NodeORM, fingerprint: str | None = None) -> None:
    """根据 node_type 路由到对应 collection 并写入。

    使用自修复模式：写入目标 collection 前，先从其他 collection 删除相同 chroma_id，确保节点
    类型变化时不会同时存在于多个 collection；调用方无需追踪 old_node_type。

    参数：
        node: 已提交到 SQLite 的最新节点。
        fingerprint: 检索文档指纹；为 None 时根据当前文档计算。
    """
    document = node_to_document(node)
    node_fingerprint = fingerprint or hashlib.sha256(f"ID: {node.id}\n{document}".encode("utf-8")).hexdigest()
    chroma_id = build_chroma_id(node.project_id, node.id)
    target_name = _resolve_collection_name(node.node_type)

    # 自修复：从非目标 collection 删除相同 chroma_id，以处理节点类型变化时的迁移。
    for name in _all_collection_names():
        if name == target_name:
            continue
        get_chroma_collection_by_name(name).delete(ids=[chroma_id])

    _log(f"upsert vector collection={target_name} chroma_id={chroma_id} node_id={node.id} title={node.title!r}")
    target_collection = get_chroma_collection_by_name(target_name)
    target_collection.upsert(
        ids=[chroma_id],
        documents=[document],
        embeddings=[embedding_provider.embed(document)],
        metadatas=[
            {
                "project_id": node.project_id,
                "node_id": node.id,
                "node_type": node.node_type,
                "title": node.title,
                "fingerprint": node_fingerprint,
                "embedding_signature": get_embedding_signature(),
            }
        ],
    )
    _log(f"upsert vector success chroma_id={chroma_id}")


def upsert_nodes(nodes: list[NodeORM]) -> None:
    """批量写入节点；不再传 collection，内部按 node_type 路由。"""
    for node in nodes:
        upsert_node(node)


def delete_node(project_id: str, node_id: str) -> None:
    """从所有 collection 删除指定 chroma_id，无需预先知道节点类型。"""
    chroma_id = build_chroma_id(project_id, node_id)
    for name in _all_collection_names():
        get_chroma_collection_by_name(name).delete(ids=[chroma_id])


def delete_nodes(project_id: str, node_ids: list[str]) -> None:
    """从所有 collection 批量删除指定 chroma_id 列表。"""
    if not node_ids:
        return

    _log(f"delete vectors project_id={project_id} node_ids={node_ids}")
    chroma_ids = [build_chroma_id(project_id, node_id) for node_id in node_ids]
    for name in _all_collection_names():
        get_chroma_collection_by_name(name).delete(ids=chroma_ids)

def query_collection(
    collection: Any,
    project_id: str,
    query: str,
    top_k: int,
    query_embedding: list[float] | None = None,
) -> tuple[list[str], list[dict], list[float]]:
    """在指定 collection 内执行项目级查询。

    collection 已按 node_type 物理隔离，因此不再需要 node_type metadata 过滤；仍保留
    project_id 过滤，防止跨项目数据泄漏到当前 prompt。

    当同一查询跨多个 collection 使用时，调用方应先用 ``embedding_provider.embed`` 预计算一次
    query_embedding 并传入，避免每个 collection 重复计算相同向量，把 embedding API 调用从 N
    次降到 1 次。

    参数：
        collection: 已按 node_type 路由好的具体 collection。
        project_id: 当前项目 ID。
        query: 检索查询；仅在未提供 query_embedding 时用于 embedding。
        top_k: 期望返回的上下文最大数量。
        query_embedding: 预计算查询向量；未传入时内部嵌入一次。

    返回：
        ChromaDB ID 列表、metadata 列表和 distance 列表。
    """
    total = collection.count()
    if total == 0:
        _log(f"query skipped collection={collection.name} reason=empty_collection")
        return [], [], []

    _log(f"query vectors collection={collection.name} project_id={project_id} top_k={top_k} total={total}")
    embedding = query_embedding if query_embedding is not None else embed_query(query)
    result = collection.query(
        query_embeddings=[embedding],
        # +1 为当前节点本身留出空间，供调用方按需过滤；同时夹到 total，避免 Chroma 抛越界参数错误。
        n_results=min(top_k + 1, total),
        where={"project_id": project_id},
        include=["metadatas", "distances"],
    )
    return (
        result.get("ids", [[]])[0],
        result.get("metadatas", [[]])[0],
        result.get("distances", [[]])[0],
    )
