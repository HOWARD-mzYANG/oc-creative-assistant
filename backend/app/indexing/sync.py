"""从 SQLite 到 ChromaDB 的索引同步策略。

SQLite 是主数据源；ChromaDB 是可重建的检索索引。本模块负责在 SQLite 事务提交后，
基于检索文档指纹执行项目级或节点级增量同步。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.db.models import NodeORM
from app.indexing.config import INDEXING_DEBUG_LOG
from app.indexing.document_loader import node_to_document
from app.indexing.vector_store import (
    delete_nodes,
    get_all_chroma_collections,
    get_embedding_signature,
    upsert_node,
)


def _log(message: str) -> None:
    """打印索引同步调试信息。
    """
    if INDEXING_DEBUG_LOG:
        print(f"[index-sync] {message}", flush=True)


@dataclass
class IndexingSyncResult:
    """向量索引同步结果。

    保存到 SQLite 是主流程；该结果只描述 ChromaDB / embedding 是否同步成功，供 API
    返回给前端作为提示。
    """

    status: str
    message: str
    provider: str
    model: str
    dimension: int
    expected_nodes: int = 0
    indexed_nodes: int = 0
    missing_node_ids: list[str] = field(default_factory=list)
    error: str | None = None


def _base_result(status: str, message: str, expected_nodes: int = 0, error: str | None = None) -> IndexingSyncResult:
    """构建统一索引状态，并集中填入当前 embedding 配置。"""
    from app.indexing.embedding_provider import embedding_provider

    return IndexingSyncResult(
        status=status,
        message=message,
        provider=embedding_provider.name,
        model=embedding_provider.model,
        dimension=embedding_provider.dimension,
        expected_nodes=expected_nodes,
        error=error,
    )


def _read_index_state(project_id: str) -> dict[str, dict[str, str]]:
    """读取当前项目在所有 collection 中已写入的 fingerprint。

    跨 collection 合并为单个 dict，因为 Plan A 下同一 node_id 总是只属于一个 collection
    （由 upsert_node 的自修复保证），因此不会有重复键。

    参数：
        project_id: 要读取索引状态的项目 ID。

    返回：
        node_id 到 fingerprint / embedding_signature 的映射。
    """
    index_state: dict[str, dict[str, str]] = {}

    for collection in get_all_chroma_collections().values():
        records = collection.get(where={"project_id": project_id}, include=["metadatas"])

        for metadata in records.get("metadatas", []) or []:
            if not isinstance(metadata, dict):
                continue

            node_id = metadata.get("node_id")
            fingerprint = metadata.get("fingerprint")
            embedding_signature = metadata.get("embedding_signature")

            if isinstance(node_id, str) and isinstance(fingerprint, str):
                index_state[node_id] = {
                    "fingerprint": fingerprint,
                    "embedding_signature": embedding_signature if isinstance(embedding_signature, str) else "",
                }

    return index_state


def build_node_fingerprint(node: NodeORM) -> str:
    """计算节点的检索文档指纹。

    指纹只基于进入检索文档的信息；不包含 position、sort_order、created_at 或 updated_at，
    因此拖动节点不会触发 embedding 更新。

    参数：
        node: 要计算指纹的 ORM 节点。

    返回：
        sha256 十六进制字符串。
    """
    # node.id 不一定进入展示文档，但必须参与指纹，避免内容相同的不同节点被误认为同一记录。
    document = f"ID: {node.id}\n{node_to_document(node)}"
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def verify_project_index(project_id: str, nodes: list[NodeORM]) -> IndexingSyncResult:
    """检查当前项目的所有节点是否都已写入对应 collection。

    参数：
        project_id: 当前项目 ID。
        nodes: SQLite 提交后的最新节点快照。

    返回：
        描述已索引数量、缺失节点和当前 embedding 配置的同步结果。
    """
    index_state = _read_index_state(project_id)
    embedding_signature = get_embedding_signature()
    missing_node_ids: list[str] = []

    for node in nodes:
        indexed_node = index_state.get(node.id, {})

        if (
            indexed_node.get("fingerprint") != build_node_fingerprint(node)
            or indexed_node.get("embedding_signature") != embedding_signature
        ):
            missing_node_ids.append(node.id)

    result = _base_result(
        status="synced" if not missing_node_ids else "partial",
        message="向量索引已同步" if not missing_node_ids else "部分节点尚未成功写入向量索引",
        expected_nodes=len(nodes),
    )
    result.indexed_nodes = len(nodes) - len(missing_node_ids)
    result.missing_node_ids = missing_node_ids
    return result


def sync_project_index_incremental(
    project_id: str,
    old_nodes: list[NodeORM],
    new_nodes: list[NodeORM],
) -> IndexingSyncResult:
    """按项目增量同步 ChromaDB 索引。

    该函数用于前端保存完整图谱快照之后。它会比较保存前后的节点指纹：新增节点或检索文档
    变化的节点会 upsert，已删除节点会 delete。

    参数：
        project_id: 要同步索引的项目 ID。
        old_nodes: 保存前的项目节点快照。
        new_nodes: SQLite 提交后的最新项目节点快照。
    """
    index_state = _read_index_state(project_id)
    embedding_signature = get_embedding_signature()
    old_fingerprints = {node.id: build_node_fingerprint(node) for node in old_nodes}
    new_fingerprints = {node.id: build_node_fingerprint(node) for node in new_nodes}
    _log(
        "start project sync "
        f"project_id={project_id} old_nodes={len(old_nodes)} new_nodes={len(new_nodes)} "
        f"indexed_records={len(index_state)} signature={embedding_signature}"
    )

    deleted_node_ids = sorted(set(old_fingerprints) - set(new_fingerprints))
    # 完整图谱保存会重写 SQLite 行，但 ChromaDB 只删除 payload 中确实消失的节点。
    delete_nodes(project_id, deleted_node_ids)

    if deleted_node_ids:
        _log(f"delete stale vectors node_ids={deleted_node_ids}")

    for node in new_nodes:
        new_fingerprint = new_fingerprints[node.id]
        old_fingerprint = old_fingerprints.get(node.id)
        indexed_node = index_state.get(node.id, {})
        indexed_fingerprint = indexed_node.get("fingerprint")
        indexed_embedding_signature = indexed_node.get("embedding_signature")
        update_reasons: list[str] = []

        if old_fingerprint is None:
            update_reasons.append("new_node")
        elif old_fingerprint != new_fingerprint:
            update_reasons.append("document_changed")

        if indexed_fingerprint != new_fingerprint:
            update_reasons.append("missing_or_stale_vector")

        if indexed_embedding_signature != embedding_signature:
            update_reasons.append("embedding_signature_changed")

        # 只有文档指纹与 embedding 配置签名同时匹配时才跳过；切换模型或维度后必须重写向量。
        if (
            old_fingerprint == new_fingerprint
            and indexed_fingerprint == new_fingerprint
            and indexed_embedding_signature == embedding_signature
        ):
            # 坐标或排序变化不影响检索文档；索引已有相同指纹时跳过 embedding 更新。
            _log(f"skip node_id={node.id} reason=fingerprint_and_embedding_signature_unchanged")
            continue

        _log(f"upsert node_id={node.id} reasons={','.join(update_reasons) or 'unknown'}")
        upsert_node(node, new_fingerprint)

    result = verify_project_index(project_id, new_nodes)
    _log(
        "finish project sync "
        f"status={result.status} indexed={result.indexed_nodes}/{result.expected_nodes} "
        f"missing={result.missing_node_ids}"
    )
    return result


def sync_node_index(node: NodeORM, old_fingerprint: str | None = None) -> IndexingSyncResult:
    """将单个节点同步到 ChromaDB。

    参数：
        node: SQLite 提交后的最新节点。
        old_fingerprint: 更新前的检索文档指纹；若相同可跳过写入。
    """
    new_fingerprint = build_node_fingerprint(node)
    _log(f"start node sync project_id={node.project_id} node_id={node.id}")

    if old_fingerprint == new_fingerprint:
        indexed_node = _read_index_state(node.project_id).get(node.id, {})
        indexed_fingerprint = indexed_node.get("fingerprint")
        indexed_embedding_signature = indexed_node.get("embedding_signature")

        # 检索文档未变时，还要确认索引由当前 embedding 配置写入；否则会混入旧模型向量。
        if indexed_fingerprint == new_fingerprint and indexed_embedding_signature == get_embedding_signature():
            result = _base_result("synced", "向量索引已同步", expected_nodes=1)
            result.indexed_nodes = 1
            _log(f"skip node_id={node.id} reason=fingerprint_and_embedding_signature_unchanged")
            return result

        # 检索字段未变但索引记录缺失时，用户通常清空过 ChromaDB 目录，因此必须从 SQLite 回填。
        _log(f"upsert node_id={node.id} reason=vector_missing_or_embedding_signature_changed")
    else:
        _log(f"upsert node_id={node.id} reason=document_changed")

    upsert_node(node, new_fingerprint)
    result = verify_project_index(node.project_id, [node])
    _log(f"finish node sync node_id={node.id} status={result.status} indexed={result.indexed_nodes}/1")
    return result


def safe_sync_project_index_incremental(
    project_id: str,
    old_nodes: list[NodeORM],
    new_nodes: list[NodeORM],
) -> IndexingSyncResult:
    """安全同步项目索引。

    当 ChromaDB 同步失败时吞掉异常，确保可重建索引不影响主 SQLite 数据保存。

    参数：
        project_id: 要同步索引的项目 ID。
        old_nodes: 保存前的项目节点快照。
        new_nodes: SQLite 提交后的最新项目节点快照。
    """
    try:
        return sync_project_index_incremental(project_id, old_nodes, new_nodes)
    except Exception as error:  # noqa: BLE001
        # SQLite 是主数据源；ChromaDB/embedding 失败不能回滚保存。错误会返回前端提示用户修配置。
        _log(f"project sync failed project_id={project_id} error={error}")
        result = _base_result(
            status="failed",
            message="已保存到 SQLite，但写入 embedding 向量索引失败",
            expected_nodes=len(new_nodes),
            error=str(error),
        )
        try:
            # 即使同步失败，也尝试读取当前 ChromaDB 状态，告诉前端哪些节点已有可用向量。
            verified = verify_project_index(project_id, new_nodes)
            result.indexed_nodes = verified.indexed_nodes
            result.missing_node_ids = verified.missing_node_ids
        except Exception:  # noqa: BLE001
            result.missing_node_ids = [node.id for node in new_nodes]
        return result


def safe_sync_node_index(node: NodeORM, old_fingerprint: str | None = None) -> IndexingSyncResult:
    """安全同步单节点索引。

    参数：
        node: SQLite 提交后的最新节点。
        old_fingerprint: 更新前的检索文档指纹；若相同可跳过写入。
    """
    try:
        return sync_node_index(node, old_fingerprint)
    except Exception as error:  # noqa: BLE001
        # 索引可从 SQLite 重建，因此这里隔离失败并把错误返回给调用方。
        _log(f"node sync failed node_id={node.id} error={error}")
        result = _base_result(
            status="failed",
            message="已保存到 SQLite，但写入该节点 embedding 向量失败",
            expected_nodes=1,
            error=str(error),
        )
        try:
            verified = verify_project_index(node.project_id, [node])
            result.indexed_nodes = verified.indexed_nodes
            result.missing_node_ids = verified.missing_node_ids
        except Exception:  # noqa: BLE001
            result.missing_node_ids = [node.id]
        return result
