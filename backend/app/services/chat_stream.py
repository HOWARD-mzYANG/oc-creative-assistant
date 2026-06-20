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
from app.agents.progress import NODE_LABELS
from app.core.settings import get_app_settings
from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.schemas import ChatRequest
from app.services.chat_service import require_session


logger = logging.getLogger(__name__)

_PROD_ERROR_MESSAGE = "推理过程中出了点问题，请稍后再试"

_INTENT_LABELS: dict[str, str] = {
    "inspiration": "灵感",
    "research": "资料",
    "structure": "结构",
    "simulation": "模拟",
    "small_talk": "对话",
}


_DONE = object()


def _sse(data: dict[str, Any]) -> str:
    """将字典转为 SSE 协议数据行（事件之间用双换行分隔）。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _traceback_tail(exc: BaseException, *, max_lines: int = 14) -> str:
    """截取异常 traceback 尾部，避免开发模式 SSE 错误事件过长。"""
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


def _clip(text: str, limit: int = 240) -> str:
    """将 trace 文本裁到适合聊天面板展示的长度。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _reasoning_of(value: Any) -> str:
    """从 Pydantic 输出对象中安全读取 reasoning 字段。"""
    reasoning = getattr(value, "reasoning", "")
    return reasoning if isinstance(reasoning, str) else str(reasoning or "")


def _trace_event(node_name: str, title: str, content: str) -> dict[str, Any]:
    """构建前端 AgentTracePanel 使用的单条思考/处理轨迹事件。"""
    return {
        "type": "trace_item",
        "node": node_name,
        "title": title,
        "content": _clip(content),
    }


def _build_trace_events(node_name: str, node_output: dict[str, Any]) -> list[dict[str, Any]]:
    """把显式 reasoning 和确定性节点摘要转换为前端可展示的思考轨迹。"""
    events: list[dict[str, Any]] = []

    if node_name == "intent_router":
        intent = node_output.get("intent")
        if intent is not None:
            primary = getattr(intent, "primary", "")
            confidence = getattr(intent, "confidence", 0)
            reasoning = _reasoning_of(intent)
            content = f"{_INTENT_LABELS.get(primary, primary)} · 置信度 {confidence:.2f}"
            if reasoning:
                content += f"\n{reasoning}"
            events.append(_trace_event(node_name, "意图判断", content))

    elif node_name == "parallel_retrieval":
        graph_count = len(node_output.get("graph_context") or [])
        vector_count = len(node_output.get("vector_context") or [])
        merged_count = len(node_output.get("merged_context") or [])
        events.append(
            _trace_event(
                node_name,
                "检索上下文",
                f"图关系 {graph_count} 条，向量命中 {vector_count} 条，合并后 {merged_count} 条。",
            )
        )

    elif node_name in {
        "inspiration_agent",
        "research_agent",
        "structure_agent",
        "simulation_agent",
    }:
        output_key = node_name.replace("_agent", "_output")
        output = node_output.get(output_key)
        reasoning = _reasoning_of(output)
        if reasoning:
            events.append(_trace_event(node_name, NODE_LABELS.get(node_name, node_name), reasoning))

    elif node_name == "boundary_check":
        warnings = node_output.get("boundary_warnings") or []
        if warnings:
            events.append(_trace_event(node_name, "边界检查", "\n".join(f"- {w}" for w in warnings)))

    elif node_name == "question_planner":
        hint = str(node_output.get("next_question_hint") or "").strip()
        reasoning = str(node_output.get("question_planner_reasoning") or "").strip()
        if hint or reasoning:
            content = reasoning
            if hint:
                content = f"{content}\n下一步追问：{hint}" if content else f"下一步追问：{hint}"
            events.append(_trace_event(node_name, "追问规划", content))

    elif node_name == "persistence_hub":
        count = int(node_output.get("staging_count") or 0)
        if count:
            events.append(_trace_event(node_name, "结果暂存", f"已生成 {count} 条待应用变更。"))

    elif node_name == "structured_extractor":
        count = int(node_output.get("extraction_count") or 0)
        reasoning = str(node_output.get("extraction_reasoning") or "").strip()
        if count or reasoning:
            content = reasoning
            if count:
                content = f"{content}\n抽取到 {count} 条结构化变更。" if content else f"抽取到 {count} 条结构化变更。"
            events.append(_trace_event(node_name, "后台抽取", content))

    elif node_name == "summary_compress" and node_output.get("conversation_summary"):
        facts = node_output.get("key_facts") or []
        events.append(_trace_event(node_name, "对话摘要", f"已更新长期摘要，保留 {len(facts)} 条关键事实。"))

    return events


def _build_events(node_name: str, node_output: Any) -> list[dict[str, Any]]:
    """将节点输出转成 SSE 事件列表（主事件 + 关键节点附带的元数据事件）。"""
    events: list[dict[str, Any]] = [
        {
            "type": "node_end",
            "node": node_name,
            "label": NODE_LABELS.get(node_name, node_name),
        }
    ]

    if not isinstance(node_output, dict):
        return events

    events.extend(_build_trace_events(node_name, node_output))

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
                    if payload.get("type") == "node_start" and isinstance(payload.get("node"), str):
                        last_node = payload["node"]
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
