"""聊天与暂存 HTTP 路由。

暴露 sessions / messages / staging 的 CRUD 端点；``POST /api/chat`` 是真正的
Agent 入口，会触发完整 LangGraph 推理流水线。
"""

from typing import Literal

from fastapi import APIRouter

from app.schemas import (
    AgentStagingActionRequest,
    AgentStagingBatchActionRequest,
    AgentStagingBatchCreateRequest,
    AgentStagingBatchPayload,
    AgentStagingPayload,
    ChatMessageCreateRequest,
    ChatMessagePayload,
    ChatRequest,
    ChatResponse,
    ChatSessionCreateRequest,
    ChatSessionPayload,
    SessionRenameRequest,
    SessionTitleRequest,
)
from app.services.chat_service import (
    append_session_message,
    delete_chat_session,
    create_session,
    create_staging_batch,
    get_session_messages,
    list_sessions,
    list_session_staging,
    resolve_staging_batch,
    resolve_staging_item,
    run_chat_turn,
    rename_chat_session,
    generate_session_title,
)
from app.services.chat_stream import stream_chat_turn
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/sessions", response_model=ChatSessionPayload)
async def create_chat_session(payload: ChatSessionCreateRequest) -> ChatSessionPayload:
    """创建新的聊天会话，并分配供 LangGraph Checkpointer 使用的 thread_id。"""
    return create_session(payload)


@router.get("/projects/{project_id}/sessions", response_model=list[ChatSessionPayload])
async def list_project_chat_sessions(project_id: str) -> list[ChatSessionPayload]:
    """列出指定项目下的会话，按创建时间倒序排列。"""
    return list_sessions(project_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_chat_session_route(session_id: str) -> None:
    """删除聊天会话及其消息 / 暂存项。"""
    delete_chat_session(session_id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionPayload)
async def rename_chat_session_route(
    session_id: str,
    payload: SessionRenameRequest,
) -> ChatSessionPayload:
    """重命名聊天会话。"""
    return rename_chat_session(session_id, payload.title)


@router.post("/sessions/{session_id}/title", response_model=ChatSessionPayload)
async def generate_chat_session_title(
    session_id: str,
    payload: SessionTitleRequest,
) -> ChatSessionPayload:
    """根据用户第一条消息生成 LLM 标题并持久化。"""
    return generate_session_title(session_id, payload.user_message)

    
@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessagePayload])
async def list_chat_messages(session_id: str) -> list[ChatMessagePayload]:
    """读取会话的完整消息历史。"""
    return get_session_messages(session_id)


@router.post("/sessions/{session_id}/messages", response_model=ChatMessagePayload)
async def append_chat_message(
    session_id: str,
    payload: ChatMessageCreateRequest,
) -> ChatMessagePayload:
    """追加单条消息（不触发 Agent 推理）；仅用于集成调试和单元测试，真实对话走 POST /api/chat。"""
    return append_session_message(session_id, payload)


@router.post("/sessions/{session_id}/staging", response_model=AgentStagingBatchPayload)
async def create_chat_staging_batch(
    session_id: str,
    payload: AgentStagingBatchCreateRequest,
) -> AgentStagingBatchPayload:
    """写入一批暂存项；persistence_hub 与手动端点共用的入口。"""
    return create_staging_batch(session_id, payload)


@router.get(
    "/sessions/{session_id}/staging",
    response_model=list[AgentStagingBatchPayload],
)
async def list_chat_staging(
    session_id: str,
    status: Literal["pending", "accepted", "edited", "rejected"] | None = None,
) -> list[AgentStagingBatchPayload]:
    """按会话列出暂存项，自动按批次分组；默认返回所有状态。"""
    return list_session_staging(session_id, status)


@router.patch("/staging/{staging_id}", response_model=AgentStagingPayload)
async def resolve_chat_staging_item(
    staging_id: str,
    payload: AgentStagingActionRequest,
) -> AgentStagingPayload:
    """接受 / 编辑 / 拒绝单条暂存项；重复操作已处理项会返回 409。"""
    return resolve_staging_item(staging_id, payload)


@router.patch(
    "/staging/batch/{batch_id}",
    response_model=list[AgentStagingPayload],
)
async def resolve_chat_staging_batch(
    batch_id: str,
    payload: AgentStagingBatchActionRequest,
) -> list[AgentStagingPayload]:
    """批量接受 / 拒绝同一回合的暂存项；已处理项会静默跳过。"""
    return resolve_staging_batch(batch_id, payload)


@router.post("/chat", response_model=ChatResponse)
async def post_chat(payload: ChatRequest) -> ChatResponse:
    """触发完整 agent_graph 推理流水线；同步返回聊天回复和暂存批次信息。"""
    return run_chat_turn(payload)


@router.post("/chat/stream")
async def post_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """SSE 流式聊天端点；前端用 fetch + ReadableStream 解析事件流。
    Cache-Control 禁用缓存，X-Accel-Buffering 禁用 nginx 中间缓冲，使事件能立即推送
    到前端，避免反向代理把事件堆成一波“突发到达”，破坏渐进式体验。
    """
    return StreamingResponse(
        stream_chat_turn(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
