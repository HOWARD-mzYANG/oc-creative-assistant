"""SSE 流式聊天实现。

LangGraph 的同步接口 `graph.stream` 与项目当前使用的 `SqliteSaver`
（同步检查点存储）兼容；直接调用 `graph.astream` 会强制走 `aget_tuple`，
需要 `AsyncSqliteSaver` + `aiosqlite`，与现有架构不匹配。

折中方案：在 `asyncio.to_thread` 中运行同步的 `graph.stream`，再通过
`asyncio.Queue` 桥接成异步生成器。这样既不用引入 aiosqlite，也不用把
chat_service.run_chat_turn 整体改成 async。
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import AsyncIterator
from typing import Any

from app.agents.graph import get_agent_graph
from app.core.settings import get_app_settings
from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.schemas import ChatRequest
from app.services.chat_service import require_session


logger = logging.getLogger(__name__)

_PROD_ERROR_MESSAGE = "推理过程中出了点问题，请稍后再试"


_NODE_LABELS: dict[str, str] = {
    "load_context": "加载上下文",
    "intent_router": "判断意图",
    "parallel_retrieval": "检索知识库",
    "context_compress": "压缩上下文",
    "inspiration_agent": "发散创意",
    "research_agent": "研究与核查",
    "structure_agent": "整理结构",
    "simulation_agent": "模拟分支",
    "boundary_check": "边界检查",
    "chat_assembler": "生成回复",
    "persistence_hub": "持久化结果",
    "structured_extractor": "提取实体",
    "question_planner": "规划追问",
    "summary_compress": "压缩对话摘要",
}


_DONE = object()


def _sse(data: dict[str, Any]) -> str:
    """将字典转为 SSE 协议数据行（事件之间用双换行分隔）。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _traceback_tail(exc: BaseException, *, max_lines: int = 14) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    lines = tb.rstrip().splitlines()
    if len(lines) <= max_lines:
        return tb.rstrip()
    omitted = len(lines) - max_lines
    return "\n".join([f"... ({omitted} lines omitted) ...", *lines[-max_lines:]])


def _build_error_event(
    exc: BaseException,
    *,
    phase: str,
    last_node: str | None = None,
) -> dict[str, Any]:
    """构建 SSE 错误载荷；仅在开发模式下包含诊断信息。"""
    if not get_app_settings().dev_mode:
        return {"type": "error", "message": _PROD_ERROR_MESSAGE}

    error_type = type(exc).__name__
    error_message = str(exc) or repr(exc)
    node_hint = f" at node `{last_node}`" if last_node else ""
    summary = f"{error_type}: {error_message}{node_hint}"

    return {
        "type": "error",
        "message": f"推理在 {phase}{node_hint} 阶段失败：{summary}",
        "debug": {
            "phase": phase,
            "last_node": last_node,
            "error_type": error_type,
            "error_message": error_message,
            "traceback": _traceback_tail(exc),
        },
    }


def _resolve_related_nodes(node_ids: list[str]) -> list[dict[str, str]]:
    """将引用节点 ID 解析为聊天 UI 需要的轻量 {id, title, node_type}。"""
    ids = list(node_ids or [])
    if not ids:
        return []
    with SessionLocal() as db:
        rows = db.query(NodeORM).filter(NodeORM.id.in_(ids)).all()
    by_id = {n.id: n for n in rows}
    return [
        {"id": n.id, "title": n.title, "node_type": n.node_type}
        for nid in ids
        if (n := by_id.get(nid)) is not None
    ]


def _build_events(node_name: str, node_output: Any) -> list[dict[str, Any]]:
    """将节点输出转成 SSE 事件列表（主事件 + 关键节点附带的元数据事件）。"""
    events: list[dict[str, Any]] = [
        {
            "type": "node_end",
            "node": node_name,
            "label": _NODE_LABELS.get(node_name, node_name),
        }
    ]

    if not isinstance(node_output, dict):
        return events

    if node_name == "intent_router":
        intent = node_output.get("intent")
        if intent is not None:
            events.append({
                "type": "intent",
                "primary": intent.primary,
                "confidence": intent.confidence,
            })

    elif node_name == "chat_assembler":
        assembler = node_output.get("assembler_output")
        if assembler is not None:
            events.append({
                "type": "reply_ready",
                "reply_text": assembler.reply_text,
                "cited_node_ids": list(assembler.cited_node_ids),
                "related_nodes": _resolve_related_nodes(assembler.cited_node_ids),
                "staging_summary": assembler.staging_summary,
                "web_sources": [item.model_dump() for item in assembler.web_sources],
            })

    elif node_name == "persistence_hub":
        events.append({
            "type": "persistence_done",
            "message_id": node_output.get("assistant_message_id", ""),
            "batch_id": node_output.get("staging_batch_id"),
            "staging_count": node_output.get("staging_count", 0),
        })
        applied = node_output.get("extraction_applied") or []
        if applied:
            events.append({"type": "extraction_applied", "items": applied})

    elif node_name == "structured_extractor":
        applied = node_output.get("extraction_applied") or []
        if applied:
            events.append({"type": "extraction_applied", "items": applied})

    return events


async def stream_chat_turn(payload: ChatRequest) -> AsyncIterator[str]:
    """运行同步的 graph.stream，并将每个节点输出转换成 SSE 事件。

    图内部的任何异常都会被收敛成单个错误事件，让前端能平滑切到兜底文案，
    而不是遇到中途断流。
    """
    with SessionLocal() as db:
        session = require_session(db, payload.session_id)
        thread_id = session.thread_id
        project_id = session.project_id

    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "session_id": payload.session_id,
        "project_id": project_id,
        "user_message": payload.user_message,
        "selected_node_ids": list(payload.selected_node_ids),
        "extraction_enabled": payload.extraction_enabled,
        "auto_apply_staging": payload.auto_apply_staging,
        "web_search_mode": payload.web_search_mode,
    }

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer() -> None:
        """同步线程运行 graph.stream；call_soon_threadsafe 将每个 chunk 送回事件循环。

        存在多个 stream_mode 时，LangGraph 会把每个 chunk 包装成 (mode, payload)
        元组；主协程按 mode 分发："updates" 是节点级更新，"custom" 是节点内通过
        get_stream_writer 推送的 token 事件。
        """
        try:
            stream = graph.stream(
                inputs, config=config, stream_mode=["updates", "custom"]
            )
            for chunk in stream:
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    producer_task = asyncio.create_task(asyncio.to_thread(producer))
    last_node: str | None = None

    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            if isinstance(item, Exception):
                logger.exception(
                    "stream_chat_turn graph internal failure (last_node=%s): %s",
                    last_node,
                    item,
                )
                yield _sse(_build_error_event(item, phase="graph.stream", last_node=last_node))
                return

            mode, payload = item
            if mode == "custom":
                # chat_assembler 通过 get_stream_writer 推送的 token 事件，原样传给前端。
                if isinstance(payload, dict) and payload.get("type"):
                    yield _sse(payload)
                continue

            # mode == "updates"：payload 是 {node_name: node_output} 字典。
            for node_name, node_output in payload.items():
                last_node = node_name
                for event in _build_events(node_name, node_output):
                    yield _sse(event)

        yield _sse({"type": "done"})

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "stream_chat_turn failed (last_node=%s): %s",
            last_node,
            exc,
        )
        yield _sse(_build_error_event(exc, phase="stream loop", last_node=last_node))
    finally:
        await producer_task
