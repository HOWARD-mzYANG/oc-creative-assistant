"""向量索引文档抽取与轻量 DTO 转换。

当前索引数据源来自画布节点。本模块负责把 ORM 节点整理成可检索文本，
并提供 RAG 响应所需的节点 DTO 转换函数。
"""

from __future__ import annotations

from typing import Any

from app.db.models import NodeORM
from app.schemas import RagCurrentNodePayload, RagVectorContextItem
from app.services.graph_mappers import db_fields_to_api


def node_to_current_payload(node: NodeORM) -> RagCurrentNodePayload:
    """将 ORM 节点转换为当前节点的 RAG DTO。

    参数：
        node: 已从 SQLite 读取出的当前节点。

    返回：
        仅包含 prompt 与前端预览所需字段的当前节点 DTO。
    """
    return RagCurrentNodePayload(
        id=node.id,
        type=node.node_type,
        title=node.title,
        content=node.content,
        tags=db_tags_to_api(node.meta),
        fields=db_fields_to_api(node.meta),
    )


def node_to_vector_item(node: NodeORM, score: float) -> RagVectorContextItem:
    """将 ORM 节点转换为向量检索结果 DTO。

    参数：
        node: 向量检索命中的节点。
        score: 相似度分数，通常位于 0 到 1 之间。

    返回：
        向量上下文响应项；分数会被四舍五入，便于前端展示。
    """
    content = (node.content or "").strip()
    fields = db_fields_to_api(node.meta)
    if fields:
        field_text = "; ".join(f"{key}: {value}" for key, value in fields.items())
        content = f"{content}\n{field_text}".strip() if content else field_text
    return RagVectorContextItem(
        id=node.id,
        type=node.node_type,
        title=node.title,
        content=content,
        score=round(score, 4),
    )


def node_to_document(node: NodeORM) -> str:
    """将节点组装成用于 embedding 的检索文档。

    标题、类型、标签和正文都会参与向量化；坐标、排序和时间戳不参与检索语义。

    参数：
        node: 写入索引或查询时用于比较的 ORM 节点。

    返回：
        用于 ChromaDB document 和阿里 embedding 的文本。
    """
    tags = ", ".join(db_tags_to_api(node.meta))
    fields = db_fields_to_api(node.meta)
    fields_block = ""
    if fields:
        fields_block = "Fields:\n" + "\n".join(f"{key}: {value}" for key, value in fields.items())
    doc = f"""Title: {node.title}
Type: {node.node_type}
Tags: {tags}
Content:
{node.content}"""
    if fields_block:
        doc = f"{doc}\n{fields_block}"
    return doc


def db_tags_to_api(meta: Any) -> list[str]:
    """从节点 meta JSON 中读取标签。

    参数：
        meta: ORM 节点的 meta 字段，可能来自旧数据库或手动编辑的数据。

    返回：
        字符串标签列表；类型异常的值会被过滤。
    """
    if isinstance(meta, dict):
        tags = meta.get("tags", [])
        return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []

    return []


_node_to_current_payload = node_to_current_payload
_node_to_vector_item = node_to_vector_item
_node_to_document = node_to_document
_db_tags_to_api = db_tags_to_api
