"""RAG 的公共服务入口。

本模块读取当前节点所属项目的图谱快照，协调图关系检索、向量检索和 prompt 组装，并返回
API 层需要的 `RagContextResponse`。
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import EdgeORM, NodeORM, ProjectORM
from app.indexing.config import MAX_TOP_K
from app.indexing.document_loader import node_to_current_payload
from app.rag.prompts import build_inspiration_prompt
from app.rag.retrieval import build_graph_context, build_project_vector_context, merge_context
from app.schemas import (
    MemorySearchItem,
    MemorySearchRequest,
    MemorySearchResponse,
    RagContextRequest,
    RagContextResponse,
    RagDebugPayload,
)
from app.services.graph_mappers import db_status_to_api, db_tags_to_api


def build_rag_context(request: RagContextRequest) -> RagContextResponse:
    """构建 Hybrid RAG 上下文预览。

    本函数只返回当前节点上下文、检索结果和 prompt，不调用真实 LLM。向量索引同步发生在
    图谱保存阶段，因此查询阶段不会向 ChromaDB 执行完整写入。

    参数：
        request: RAG API 请求体。

    返回：
        当前节点、图关系上下文、向量上下文、合并上下文、prompt 和调试信息。

    抛出：
        HTTPException: agent 类型不支持或当前节点不存在时抛出。
    """
    if request.agent_type != "inspiration":
        raise HTTPException(status_code=400, detail="此 PoC 仅支持 inspiration agent")

    # 限制 top_k，避免单次请求向 prompt 注入过多节点，影响调试可读性并增加下游 LLM 成本。
    top_k = max(1, min(request.top_k, MAX_TOP_K))

    with SessionLocal() as session:
        current_node = session.get(NodeORM, request.node_id)

        if current_node is None:
            raise HTTPException(status_code=404, detail="未找到节点")

        project_id = current_node.project_id
        nodes = session.scalars(
            select(NodeORM).where(NodeORM.project_id == project_id).order_by(NodeORM.sort_order, NodeORM.created_at)
        ).all()
        edges = session.scalars(
            select(EdgeORM).where(EdgeORM.project_id == project_id).order_by(EdgeORM.sort_order, EdgeORM.created_at)
        ).all()

    current_payload = node_to_current_payload(current_node)
    query_used = request.query.strip() or f"{current_node.title}\n{current_node.content}".strip()
    graph_context = build_graph_context(current_node.id, nodes, edges)
    vector_context, vector_store, vector_error = build_project_vector_context(
        project_id, nodes, query_used, top_k + 1
    )
    vector_context = [item for item in vector_context if item.id != current_node.id][:top_k]
    merged_context = merge_context(graph_context, vector_context)
    prompt = build_inspiration_prompt(current_payload, graph_context, vector_context, query_used)

    return RagContextResponse(
        current_node=current_payload,
        graph_context=graph_context,
        vector_context=vector_context,
        merged_context=merged_context,
        prompt=prompt,
        debug=RagDebugPayload(
            query_used=query_used,
            top_k=top_k,
            vector_store=vector_store,
            llm_called=False,
            vector_error=vector_error,
        ),
    )


def search_project_memory(project_id: str, request: MemorySearchRequest) -> MemorySearchResponse:
    """搜索当前项目的 Lore Memory。

    本函数只执行项目内向量检索并返回记忆卡片；不构建 prompt，也不调用 LLM。

    参数：
        project_id: 当前项目 ID。
        request: 项目级搜索条件。

    返回：
        当前项目内语义相关的记忆条目和调试状态。

    抛出：
        HTTPException: 项目不存在时抛出。
    """
    top_k = max(1, min(request.top_k, MAX_TOP_K))
    query_used = request.query.strip()

    with SessionLocal() as session:
        project = session.get(ProjectORM, project_id)

        if project is None:
            raise HTTPException(status_code=404, detail="未找到项目")

        nodes = session.scalars(
            select(NodeORM).where(NodeORM.project_id == project_id).order_by(NodeORM.sort_order, NodeORM.created_at)
        ).all()

    vector_context, vector_store, vector_error = build_project_vector_context(
        project_id,
        nodes,
        query_used,
        top_k,
        request.node_type,
    )
    node_by_id = {node.id: node for node in nodes}
    items: list[MemorySearchItem] = []

    for item in vector_context:
        node = node_by_id.get(item.id)

        if node is None:
            continue

        items.append(
            MemorySearchItem(
                id=node.id,
                type=node.node_type,
                title=node.title,
                content=node.content,
                tags=db_tags_to_api(node.meta),
                status=db_status_to_api(node.meta),
                score=item.score,
            )
        )

    return MemorySearchResponse(
        items=items,
        debug=RagDebugPayload(
            query_used=query_used,
            top_k=top_k,
            vector_store=vector_store,
            llm_called=False,
            vector_error=vector_error,
        ),
    )
