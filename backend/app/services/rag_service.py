"""RAG 服务层入口。

当前 RAG 核心逻辑位于 `app.rag.service`。保留这个服务层模块，是为了让 API 层只依赖
`app.services`，并方便以后接入更多 agent 时在这里统一编排。
"""

from app.rag.service import build_rag_context, search_project_memory

__all__ = ["build_rag_context", "search_project_memory"]
