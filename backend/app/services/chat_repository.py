"""聊天与暂存相关的数据库操作辅助函数。

这里是服务层与 ORM 之间的持久化边界，负责 sessions、messages、staging 三张表的
CRUD。事务策略与 graph_repository 保持一致：写操作由调用方包在
``SessionLocal.begin`` 事务中，读操作各自打开独立 session。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentStagingORM, ChatMessageORM, ChatSessionORM
from app.schemas import AgentStagingCreateItem


def new_id() -> str:
    """生成 32 字符十六进制 UUID，用作表主键和 LangGraph thread_id。"""
    return uuid.uuid4().hex


def require_session(db: Session, session_id: str) -> ChatSessionORM:
    """读取 session 并确认存在；不存在则抛 404。"""
    session = db.get(ChatSessionORM, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="未找到聊天会话")
    return session


def require_message(db: Session, message_id: str) -> ChatMessageORM:
    """读取 message 并确认存在；不存在则抛 404。"""
    message = db.get(ChatMessageORM, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="未找到聊天消息")
    return message


def require_staging(db: Session, staging_id: str) -> AgentStagingORM:
    """读取暂存记录并确认存在；不存在则抛 404。"""
    record = db.get(AgentStagingORM, staging_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到暂存项")
    return record


def insert_session(db: Session, *, project_id: str, title: str = "") -> ChatSessionORM:
    """创建 session 并自动分配 ID；``thread_id`` 一对一复用同一个 ID。"""
    session_id = new_id()
    record = ChatSessionORM(
        id=session_id,
        project_id=project_id,
        thread_id=session_id,
        title=title,
        conversation_summary="",
    )
    db.add(record)
    db.flush()
    return record


def list_project_sessions(db: Session, project_id: str) -> list[ChatSessionORM]:
    """列出项目下的会话，最新创建的排在前面。"""
    return list(
        db.scalars(
            select(ChatSessionORM)
            .where(
                ChatSessionORM.project_id == project_id,
                ~ChatSessionORM.thread_id.like("role-model-chat:%"),
            )
            .order_by(ChatSessionORM.created_at.desc())
        )
    )


def delete_session(db: Session, session_id: str) -> None:
    """删除 session；messages / staging 通过 FK ondelete=CASCADE 级联删除。"""
    record = require_session(db, session_id)
    db.delete(record)
    db.flush()


def rename_session(db: Session, session_id: str, title: str) -> ChatSessionORM:
    """更新 session 标题。"""
    record = require_session(db, session_id)
    record.title = title
    db.flush()
    return record

    
def list_session_messages(db: Session, session_id: str) -> list[ChatMessageORM]:
    """按时间顺序列出会话消息。"""
    return list(
        db.scalars(
            select(ChatMessageORM)
            .where(ChatMessageORM.session_id == session_id)
            .order_by(ChatMessageORM.created_at)
        )
    )


def append_message(
    db: Session,
    *,
    session_id: str,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ChatMessageORM:
    """追加消息，不修改已有记录。"""
    record = ChatMessageORM(
        id=new_id(),
        session_id=session_id,
        role=role,
        content=content,
        meta=meta or {},
    )
    db.add(record)
    db.flush()
    return record


def insert_staging_batch(
    db: Session,
    *,
    session_id: str,
    message_id: str,
    project_id: str,
    agent_type: str,
    items: list[AgentStagingCreateItem],
) -> tuple[str, list[AgentStagingORM]]:
    """将同一 Agent 回合的多项变更写入 staging 表，并共享一个 batch_id。"""
    batch_id = new_id()
    records: list[AgentStagingORM] = []
    for index, item in enumerate(items):
        record = AgentStagingORM(
            id=new_id(),
            session_id=session_id,
            message_id=message_id,
            project_id=project_id,
            batch_id=batch_id,
            change_type=item.change_type,
            target_id=item.target_id,
            pending_id=item.pending_id,
            payload=item.payload,
            payload_edited=None,
            agent_type=agent_type,
            reasoning=item.reasoning,
            order_in_batch=index,
            status="pending",
        )
        db.add(record)
        records.append(record)
    db.flush()
    return batch_id, records


def list_staging_by_session(
    db: Session,
    session_id: str,
    status: str | None = None,
) -> list[AgentStagingORM]:
    """按会话列出暂存项，可按状态过滤；按批次创建时间 + 批次内顺序排序。"""
    stmt = (
        select(AgentStagingORM)
        .where(AgentStagingORM.session_id == session_id)
        .order_by(AgentStagingORM.created_at, AgentStagingORM.order_in_batch)
    )
    if status:
        stmt = stmt.where(AgentStagingORM.status == status)
    return list(db.scalars(stmt))


def list_staging_by_project(
    db: Session,
    project_id: str,
    status: str | None = None,
) -> list[AgentStagingORM]:
    """按项目列出暂存项（first_revision 第 4 阶段：ChatWorkspace 跨会话待审核聚合）。"""
    stmt = (
        select(AgentStagingORM)
        .where(AgentStagingORM.project_id == project_id)
        .order_by(AgentStagingORM.created_at, AgentStagingORM.order_in_batch)
    )
    if status:
        stmt = stmt.where(AgentStagingORM.status == status)
    return list(db.scalars(stmt))


def list_staging_by_batch(db: Session, batch_id: str) -> list[AgentStagingORM]:
    """读取指定批次的所有变更，并按批次内顺序返回。"""
    return list(
        db.scalars(
            select(AgentStagingORM)
            .where(AgentStagingORM.batch_id == batch_id)
            .order_by(AgentStagingORM.order_in_batch)
        )
    )


def transition_staging(
    record: AgentStagingORM,
    *,
    new_status: str,
    payload_edited: dict[str, Any] | None = None,
) -> None:
    """状态机转移；只允许从 pending 转出，重复操作已处理记录会返回 409。"""
    if record.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"暂存项已处理（status={record.status}）",
        )
    record.status = new_status
    record.resolved_at = datetime.now(timezone.utc)
    if payload_edited is not None:
        record.payload_edited = payload_edited

def update_session_summary(
    db: Session,
    *,
    session_id: str,
    summary: str,
    key_facts: list[str],
    message_count: int,
) -> None:
    """写回对话摘要、核心事实层与高水位标记；记录不存在时静默跳过。

    key_facts 设计为“累积合并”：新事实会与旧事实去重后追加，因此早期积累的关键设定
    不会被本轮覆盖。重复事实用忽略大小写 + 去空白的粗略方式检测，以吸收 LLM 可能
    反复表达的内容。
    """
    record = db.get(ChatSessionORM, session_id)
    if record is None:
        return
    record.conversation_summary = summary

    existing = list(record.key_facts or [])
    seen = {fact.strip().lower() for fact in existing}
    for fact in key_facts:
        normalized = fact.strip()
        if normalized and normalized.lower() not in seen:
            existing.append(normalized)
            seen.add(normalized.lower())
    record.key_facts = existing

    record.summary_message_count = message_count
