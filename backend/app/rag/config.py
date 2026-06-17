"""RAG 配置兼容模块。

RAG 与向量索引共用一部分检索配置；真实配置来源位于 `app.indexing.config`。保留这个模块，是为了
让 RAG 内部 import 的语义更清晰。
"""

from app.indexing.config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_PATH,
    DEFAULT_NODE_STATUS,
    DEFAULT_RELATION_LABEL,
    DEFAULT_RELATION_TYPE,
    EMBEDDING_DIMENSION,
    MAX_TOP_K,
)

__all__ = [
    "CHROMA_COLLECTION_NAME",
    "CHROMA_PATH",
    "DEFAULT_NODE_STATUS",
    "DEFAULT_RELATION_LABEL",
    "DEFAULT_RELATION_TYPE",
    "EMBEDDING_DIMENSION",
    "MAX_TOP_K",
]
