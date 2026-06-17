"""RAG HTTP 路由。

当前 RAG API 只做上下文预览，方便前端调试 Agent 将要看到的输入，
不会触发真实 LLM 调用。
"""

from fastapi import APIRouter

from app.schemas import RagContextRequest, RagContextResponse
from app.services.rag_service import build_rag_context


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/context", response_model=RagContextResponse)
async def read_rag_context(payload: RagContextRequest) -> RagContextResponse:
    """为当前节点构建 Hybrid RAG 上下文和 Inspiration Agent prompt。"""
    return build_rag_context(payload)
