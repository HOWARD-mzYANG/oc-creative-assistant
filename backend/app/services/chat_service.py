"""聊天与暂存的应用服务层。

对外提供语义化操作：创建会话、追加消息、列出消息，以及推进暂存状态机。
完整推理链由 ``run_chat_turn`` 触发，普通消息写入只负责持久化与状态机。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from fastapi import HTTPException

from app.agents.graph import get_agent_graph
from langchain_core.messages import HumanMessage, SystemMessage
from app.llm.factory import get_llm_provider
from app.db.database import SessionLocal
from app.db.models import AgentStagingORM, ChatMessageORM, ChatSessionORM, NodeORM
from app.indexing.sync import safe_sync_node_index
from app.indexing.vector_store import delete_node as delete_node_vectors
from app.services.canvas_apply import apply_staging_record
from app.services.graph_repository import read_project_node, require_project
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
)
from app.services.chat_repository import (
    append_message,
    delete_session,
    insert_session,
    list_project_sessions,
    list_session_messages,
    list_staging_by_batch,
    list_staging_by_project,
    list_staging_by_session,
    rename_session,
    require_message,
    require_session,
    require_staging,
    transition_staging,
)


# ---- ORM → DTO ----

def _session_to_payload(record: ChatSessionORM) -> ChatSessionPayload:
    """把聊天会话 ORM 记录转换为 API DTO。"""
    return ChatSessionPayload(
        id=record.id,
        project_id=record.project_id,
        thread_id=record.thread_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _message_to_payload(record: ChatMessageORM) -> ChatMessagePayload:
    """把聊天消息 ORM 记录转换为 API DTO。"""
    return ChatMessagePayload(
        id=record.id,
        session_id=record.session_id,
        role=record.role,
        content=record.content,
        meta=record.meta,
        created_at=record.created_at,
    )


def _display_payload_for_staging(record: AgentStagingORM, db) -> dict[str, Any]:
    """为前端展示补全 staging payload，不修改数据库中 LLM 原始输出。"""
    payload = dict(record.payload_edited or record.payload or {})
    if record.change_type != "update_node" or not record.target_id:
        return payload

    node = db.get(NodeORM, record.target_id)
    if node is None or node.project_id != record.project_id:
        return payload

    payload.setdefault("title", node.title)
    payload.setdefault("content", node.content)
    payload.setdefault("node_type", node.node_type)
    return payload


def _staging_to_payload(record: AgentStagingORM, db) -> AgentStagingPayload:
    """把暂存变更 ORM 记录转换为前端可展示的 API DTO。"""
    return AgentStagingPayload(
        id=record.id,
        session_id=record.session_id,
        message_id=record.message_id,
        project_id=record.project_id,
        batch_id=record.batch_id,
        change_type=record.change_type,
        target_id=record.target_id,
        pending_id=record.pending_id,
        payload=_display_payload_for_staging(record, db),
        payload_edited=record.payload_edited,
        agent_type=record.agent_type,
        reasoning=record.reasoning,
        order_in_batch=record.order_in_batch,
        status=record.status,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )


def _group_by_batch(records: list[AgentStagingORM], db) -> list[AgentStagingBatchPayload]:
    """按 batch_id 聚合，保留批次首次出现顺序；批次内保留 order_in_batch。"""
    grouped: dict[str, list[AgentStagingORM]] = {}
    order: list[str] = []
    for record in records:
        if record.batch_id not in grouped:
            grouped[record.batch_id] = []
            order.append(record.batch_id)
        grouped[record.batch_id].append(record)
    return [
        AgentStagingBatchPayload(
            batch_id=batch_id,
            items=[_staging_to_payload(r, db) for r in grouped[batch_id]],
        )
        for batch_id in order
    ]


# ---- Session ----

def create_session(payload: ChatSessionCreateRequest) -> ChatSessionPayload:
    """创建新会话，并确认项目存在。"""
    with SessionLocal.begin() as db:
        require_project(db, payload.project_id)
        record = insert_session(db, project_id=payload.project_id, title=payload.title)
        return _session_to_payload(record)


def list_sessions(project_id: str) -> list[ChatSessionPayload]:
    """列出指定项目下的会话，并确认项目存在。"""
    with SessionLocal() as db:
        require_project(db, project_id)
        return [_session_to_payload(r) for r in list_project_sessions(db, project_id)]


def delete_chat_session(session_id: str) -> None:
    """删除会话及其消息 / 暂存项（级联删除）。"""
    with SessionLocal.begin() as db:
        delete_session(db, session_id)


def rename_chat_session(session_id: str, title: str) -> ChatSessionPayload:
    """重命名会话；空标题回退为占位标题。"""
    with SessionLocal.begin() as db:
        record = rename_session(db, session_id, title.strip() or "未命名聊天")
        return _session_to_payload(record)


_TITLE_SYSTEM = (
    "你负责为聊天会话命名。请只根据用户第一条消息给出一个很短的标题，"
    "并使用用户的语言：英文最多 4 个词，中文最多 5 个汉字。"
    "不要引号、不要标点、不要解释，只输出核心主题。"
)


def _summarize_title(user_message: str) -> str:
    """让 LLM 生成短会话标题；失败时回退为截断文本。"""
    text = user_message.strip()
    if not text:
        return "新聊天"
    try:
        reply = get_llm_provider().chat(
            [SystemMessage(content=_TITLE_SYSTEM), HumanMessage(content=text)]
        )
        title = (reply or "").strip().strip('"').strip().splitlines()[0].strip()
        return title[:14] or text[:10]
    except Exception as error:  # noqa: BLE001
        logger.warning("会话标题生成失败，回退到截断文本：%s", error)
        return text[:10]


def generate_session_title(session_id: str, user_message: str) -> ChatSessionPayload:
    """将用户第一条消息概括成标题并持久化。"""
    title = _summarize_title(user_message)
    with SessionLocal.begin() as db:
        record = rename_session(db, session_id, title)
        return _session_to_payload(record)

# ---- 消息 ----

def append_session_message(
    session_id: str,
    payload: ChatMessageCreateRequest,
) -> ChatMessagePayload:
    """向指定会话追加消息但不触发 agent_graph；仅用于集成调试和单元测试。
    生产聊天流程由 ``run_chat_turn`` 处理，它会在图节点内统一写入消息。"""
    with SessionLocal.begin() as db:
        require_session(db, session_id)
        record = append_message(
            db,
            session_id=session_id,
            role=payload.role,
            content=payload.content,
            meta=payload.meta,
        )
        return _message_to_payload(record)


def get_session_messages(session_id: str) -> list[ChatMessagePayload]:
    """读取会话中的所有消息。"""
    with SessionLocal() as db:
        require_session(db, session_id)
        return [_message_to_payload(r) for r in list_session_messages(db, session_id)]


# ---- 暂存 ----

def create_staging_batch(
    session_id: str,
    payload: AgentStagingBatchCreateRequest,
) -> AgentStagingBatchPayload:
    """写入一批暂存项；persistence_hub 和手动接口都会走这条路径。"""
    with SessionLocal.begin() as db:
        session = require_session(db, session_id)
        require_message(db, payload.message_id)
        batch_id, records = insert_staging_batch(
            db,
            session_id=session_id,
            message_id=payload.message_id,
            project_id=session.project_id,
            agent_type=payload.agent_type,
            items=payload.items,
        )
        return AgentStagingBatchPayload(
            batch_id=batch_id,
            items=[_staging_to_payload(r, db) for r in records],
        )


def list_session_staging(
    session_id: str,
    status: str | None = None,
) -> list[AgentStagingBatchPayload]:
    """按会话列出暂存项，并自动按批次分组。"""
    with SessionLocal() as db:
        require_session(db, session_id)
        records = list_staging_by_session(db, session_id, status)
        return _group_by_batch(records, db)


def list_project_staging(
    project_id: str,
    status: str | None = None,
) -> list[AgentStagingBatchPayload]:
    """按项目列出暂存项，并自动按批次分组（供 ChatWorkspace 待审核面板使用）。"""
    with SessionLocal() as db:
        require_project(db, project_id)
        records = list_staging_by_project(db, project_id, status)
        return _group_by_batch(records, db)


def resolve_staging_item(
    staging_id: str,
    payload: AgentStagingActionRequest,
) -> AgentStagingPayload:
    """推进单条暂存记录的状态机；accept / edit 时同时把变更应用到画布。
    """
    upserted: list[tuple[str, str]] = []
    deleted: list[tuple[str, str]] = []

    with SessionLocal.begin() as db:
        record = require_staging(db, staging_id)

        if payload.action == "accept":
            transition_staging(record, new_status="accepted")
        elif payload.action == "edit":
            if payload.payload_edited is None:
                raise HTTPException(
                    status_code=400,
                    detail="action='edit' 时必须提供 payload_edited",
                )
            transition_staging(
                record,
                new_status="edited",
                payload_edited=payload.payload_edited,
            )
        else:
            transition_staging(record, new_status="rejected")

        # 单条接受 create_edge 时，主动查找同批次中已经接受的 create_node，
        # 以重建 pending_id_map；其他 change_type 不需要该映射，空字典即可。
        pending_id_map: dict[str, str] = {}
        if record.change_type == "create_edge":
            siblings = list_staging_by_batch(db, record.batch_id)
            for sibling in siblings:
                if (
                    sibling.change_type == "create_node"
                    and sibling.status in {"accepted", "edited"}
                    and sibling.pending_id
                    and sibling.target_id
                ):
                    pending_id_map[sibling.pending_id] = sibling.target_id

        upserted_id, deleted_id = apply_staging_record(db, record, pending_id_map)
        if upserted_id:
            upserted.append((record.project_id, upserted_id))
        if deleted_id:
            deleted.append((record.project_id, deleted_id))

        result = _staging_to_payload(record, db)

    _sync_indices(upserted)
    _sync_deletions(deleted)
    return result


def resolve_staging_batch(
    batch_id: str,
    payload: AgentStagingBatchActionRequest,
) -> list[AgentStagingPayload]:
    """批量推进暂存项；已处理项会静默跳过，accept_all 时还会应用到画布。

    create_edge 依赖 pending_id 到真实 node_id 的解析；pending_id_map 分两步填充：
    1. 循环前先扫描记录，找出“之前已被单条接受的 create_node”的 pending_id -> target_id，
       避免同批次边因为前置节点已经被处理而被跳过；
    2. 循环中继续累积本次 accept_all 新创建节点的映射。
    如果没有这一步预热，当用户混合使用“先单条接受节点，再接受剩余全部”时，引用前置
    pending_id 的边会被 _resolve_endpoint 当作假 ID，最终整条边被静默跳过。
    """
    new_status = "accepted" if payload.action == "accept_all" else "rejected"
    upserted: list[tuple[str, str]] = []
    deleted: list[tuple[str, str]] = []
    pending_id_map: dict[str, str] = {}

    with SessionLocal.begin() as db:
        records = list_staging_by_batch(db, batch_id)
        if not records:
            raise HTTPException(status_code=404, detail="未找到暂存批次")

        for record in records:
            if (
                record.change_type == "create_node"
                and record.status in {"accepted", "edited"}
                and record.pending_id
                and record.target_id
            ):
                pending_id_map[record.pending_id] = record.target_id

        ordered = sorted(
            records,
            key=lambda r: (0 if r.change_type == "create_node" else 1, r.order_in_batch),
        )

        for record in ordered:
            if record.status != "pending":
                continue
            transition_staging(record, new_status=new_status)
            upserted_id, deleted_id = apply_staging_record(db, record, pending_id_map)
            if upserted_id:
                upserted.append((record.project_id, upserted_id))
            if deleted_id:
                deleted.append((record.project_id, deleted_id))

        results = [_staging_to_payload(r, db) for r in records]

    _sync_indices(upserted)
    _sync_deletions(deleted)
    return results


# ---- Agent 回合 ----

def run_chat_turn(payload: ChatRequest) -> ChatResponse:
    """运行 Agent 的完整推理链，返回组装后的回复与暂存批次信息。

    本函数不会在 graph.invoke 前手动写入 user_message；写入统一由 persistence_hub
    节点处理，使消息顺序严格对应同一事务边界内的 LLM 推理过程。

    图内部任何异常（LLM 超时 / 解析错误 / 节点 KeyError）都会收敛成 200 +
    兜底 ChatResponse，避免前端出现 500 -> fetch failed -> 空白界面；实际诊断依赖
    后端日志中的异常 traceback。
    """
    with SessionLocal() as db:
        session = require_session(db, payload.session_id)
        thread_id = session.thread_id
        project_id = session.project_id

    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = graph.invoke(
            {
                "session_id": payload.session_id,
                "project_id": project_id,
                "user_message": payload.user_message,
                "selected_node_ids": list(payload.selected_node_ids),
                "extraction_enabled": payload.extraction_enabled,
                "auto_apply_staging": payload.auto_apply_staging,
                "web_search_mode": payload.web_search_mode,
                "preferred_intent": payload.preferred_intent,
            },
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("graph.invoke failed, returning fallback reply: %s", exc)
        return ChatResponse(
            message_id="",
            reply_text="抱歉，这轮内部推理出了点问题。请再说一次，或换个说法试试。",
            cited_node_ids=[],
            intent="",
            batch_id=None,
            staging_count=0,
            staging_summary="",
        )

    assembler = final_state.get("assembler_output")
    intent = final_state.get("intent")
    intent_name = intent.primary if intent is not None else ""

    if assembler is None:
        return ChatResponse(
            message_id="",
            reply_text="这轮我没有得到合适的结果。可以再多告诉我一点你想要的方向吗？",
            cited_node_ids=[],
            intent=intent_name,
            batch_id=None,
            staging_count=0,
            staging_summary="",
        )

    return ChatResponse(
        message_id=final_state.get("assistant_message_id", ""),
        reply_text=assembler.reply_text,
        cited_node_ids=list(assembler.cited_node_ids),
        intent=intent_name,
        batch_id=final_state.get("staging_batch_id"),
        staging_count=final_state.get("staging_count", 0),
        staging_summary=assembler.staging_summary,
    )

def _sync_indices(items: list[tuple[str, str]]) -> None:
    """为刚持久化的节点触发 ChromaDB 同步；必须等事务提交后执行以避免脏写。"""
    for project_id, node_id in items:
        node = read_project_node(project_id, node_id)
        if node is not None:
            safe_sync_node_index(node)


def _sync_deletions(items: list[tuple[str, str]]) -> None:
    """为刚删除的节点移除 ChromaDB 向量；必须等事务提交后执行以避免脏写。

    Chroma 失败不会回滚 SQLite 删除：主数据源已经移除了它，残留向量之后再次调用
    delete_node 即可清理；日志只作为排查线索保留。
    """
    for project_id, node_id in items:
        try:
            delete_node_vectors(project_id, node_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "delete chroma failed project=%s node=%s: %s", project_id, node_id, exc
            )
