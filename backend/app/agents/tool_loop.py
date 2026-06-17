"""工具调用执行循环。

封装“调用 LLM -> 查看 tool_calls -> 执行 -> 把结果喂回 LLM”的 ReAct 循环，让 agent 节点
只关心起始 prompt 和最终结构化输出。MAX_TOOL_LOOPS=3 让 LLM 能真正做多轮决策：第 1 轮
调用初始工具，第 2-3 轮查看结果并决定继续查询还是收束；实践中需要超过 3 轮的场景很少，
这也能拦住 LLM 无限循环。

工具调用预算有双重上限：单轮批次 <= MAX_CALLS_PER_BATCH，防止 LLM 一次并行发出大量相似查询；
跨轮总数 <= MAX_TOTAL_TOOL_CALLS，防止 LLM 跨轮重复发出同一查询。

``compact_history_for_structured`` 会把循环后的历史压平为纯 SystemMessage + HumanMessage
序列，避免后续 ``with_structured_output`` 的 function_calling parser 把旧 tool_calls 当作
“unknown tool”并抛 KeyError。工具结果按 token（不是字符）截断，因此 list_nodes 这类一次返回
几十条 JSON 的工具不会被切掉关键内容；中间说明对长度不那么敏感，仍按字符截断。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.agents.token_budget import truncate_tokens
from app.core.settings import get_llm_settings
from app.llm.provider import LlmProvider, extract_provider_reasoning

# 模型最多规划几轮工具调用。
MAX_TOOL_LOOPS = 4

# 每一轮里最多允许并行/批量调用几个工具。
MAX_CALLS_PER_BATCH = 5

# 整轮对话里工具调用总次数上限。
MAX_TOTAL_TOOL_CALLS = 20
_TOOL_RESULT_TOKEN_CAP = 2000
_MIDDLE_THOUGHT_CHAR_CAP = 400
_TOOL_TRACE_PREVIEW_CHAR_CAP = 180


def run_tool_loop(
    provider: LlmProvider,
    initial_messages: list[BaseMessage],
    tools: list[BaseTool],
    trace_callback: Callable[[dict[str, str]], None] | None = None,
) -> list[BaseMessage]:
    """运行工具调用循环直到结束，返回包含所有 tool_calls / tool_results 的消息历史。

    协议关键点：AIMessage.tool_calls 中的“每个”调用都必须配对一个 ToolMessage；哪怕少一个，
    下一次 chat_with_tools 都会触发 OpenAI 协议 400（tool_calls 后的 tool messages 不足）。
    因此迭代总会跑完所有 tool_calls，超预算的不会实际调用，而是用占位 ToolMessage 通知 LLM
    “已跳过，请直接收束”。
    """
    tool_by_name = {tool.name: tool for tool in tools}
    history: list[BaseMessage] = list(initial_messages)
    total_calls = 0
    writer = _get_optional_stream_writer()
    stream_reasoning = get_llm_settings().stream_reasoning

    for loop_index in range(MAX_TOOL_LOOPS):
        _emit_trace_item(
            writer,
            "工具规划",
            f"正在判断是否需要调用项目工具（第 {loop_index + 1} 轮）。",
            trace_callback=trace_callback,
        )
        response = provider.chat_with_tools(history, tools)
        if stream_reasoning:
            _emit_provider_reasoning(writer, response)
        history.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            _emit_trace_item(
                writer,
                "工具规划",
                "模型认为已有证据足够，结束工具调用。",
                trace_callback=trace_callback,
            )
            return history

        for idx, call in enumerate(tool_calls):
            tool_name = str(call.get("name") or "unknown_tool")
            tool_args = call.get("args", {})
            _emit_trace_item(
                writer,
                "工具调用",
                f"{tool_name}({_format_tool_args(tool_args)})",
                trace_callback=trace_callback,
            )
            started = time.perf_counter()
            within_batch = idx < MAX_CALLS_PER_BATCH
            within_budget = total_calls < MAX_TOTAL_TOOL_CALLS
            if not within_batch or not within_budget:
                content = (
                    "[已跳过：本轮工具调用超出预算"
                    f"（每轮最多 {MAX_CALLS_PER_BATCH} 次，总预算 {MAX_TOTAL_TOOL_CALLS} 次）。"
                    "请直接基于已有证据收束，不要再调用工具。]"
                )
            else:
                tool_fn = tool_by_name.get(tool_name)
                if tool_fn is None:
                    content = f"未知工具：{tool_name}"
                else:
                    try:
                        content = tool_fn.invoke(tool_args)
                    except Exception as exc:  # noqa: BLE001
                        content = f"工具执行失败：{exc}"
                total_calls += 1
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            _emit_trace_item(
                writer,
                "工具结果",
                (
                    f"{tool_name} 完成，用时 {elapsed_ms}ms。\n"
                    f"{_format_tool_result_preview(content)}"
                ),
                trace_callback=trace_callback,
            )
            history.append(ToolMessage(content=str(content), tool_call_id=call["id"]))

        if total_calls >= MAX_TOTAL_TOOL_CALLS:
            return history

    return history


def _get_optional_stream_writer():
    """尽力获取 LangGraph custom stream writer；非流式调用下返回 None。"""
    try:
        return get_stream_writer()
    except Exception:
        return None


def _emit_provider_reasoning(writer, response: AIMessage) -> None:
    """把 provider 返回的 reasoning_content 透传给前端；失败时静默跳过。"""
    if writer is None:
        return
    reasoning = extract_provider_reasoning(response)
    if not reasoning:
        return
    try:
        writer({"type": "reasoning_token", "text": reasoning})
    except Exception:
        pass


def _emit_trace_item(
    writer,
    title: str,
    content: str,
    *,
    node: str = "tool_loop",
    trace_callback: Callable[[dict[str, str]], None] | None = None,
) -> None:
    """向前端推送工具循环中的实时可观察轨迹。"""
    payload = {
        "type": "trace_item",
        "node": node,
        "title": title,
        "content": _truncate_chars(content, 480),
    }
    if trace_callback is not None:
        try:
            trace_callback(payload)
        except Exception:
            pass
    if writer is None:
        return
    try:
        writer(payload)
    except Exception:
        pass


def emit_trace_item(title: str, content: str, *, node: str = "agent") -> None:
    """给 agent 节点复用的便捷 trace 推送入口。"""
    _emit_trace_item(_get_optional_stream_writer(), title, content, node=node)


def _format_tool_args(args: object) -> str:
    """把工具参数压成适合在前端展示的一行文本。"""
    try:
        return json.dumps(args, ensure_ascii=False)
    except TypeError:
        return str(args)


def _format_tool_result_preview(content: object) -> str:
    """把工具返回值整理成更短的前端预览，完整内容仍会进入 LLM 历史。"""
    if isinstance(content, (list, dict)):
        data = content
    else:
        text = str(content).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return _truncate_chars(text, _TOOL_TRACE_PREVIEW_CHAR_CAP)

    if isinstance(data, list):
        if not data:
            return "返回 0 条结果。"
        preview_items = [_summarize_tool_item(item) for item in data[:2]]
        suffix = f"\n…共 {len(data)} 条结果" if len(data) > 2 else f"\n共 {len(data)} 条结果"
        return "\n".join(preview_items) + suffix

    if isinstance(data, dict):
        if {"id", "title", "type"} & data.keys():
            return _summarize_tool_item(data)
        if "answer" in data or "hits" in data:
            answer = _truncate_chars(str(data.get("answer") or ""), 120)
            hits = data.get("hits") if isinstance(data.get("hits"), list) else []
            return f"answer: {answer or '无'}\n来源 {len(hits)} 条"
        keys = ", ".join(list(data.keys())[:6])
        return f"返回对象：{keys}"

    return _truncate_chars(str(content), _TOOL_TRACE_PREVIEW_CHAR_CAP)


def _summarize_tool_item(item: object) -> str:
    """摘要化单条工具结果，避免在 trace 面板里展示大段 JSON。"""
    if not isinstance(item, dict):
        return _truncate_chars(str(item), _TOOL_TRACE_PREVIEW_CHAR_CAP)

    title = str(item.get("title") or item.get("id") or "未命名")
    item_type = str(item.get("type") or item.get("node_type") or "")
    item_id = str(item.get("id") or "")
    score = item.get("score")
    preview = str(item.get("content_preview") or item.get("content") or item.get("snippet") or "")
    head_parts = [title]
    if item_type:
        head_parts.append(item_type)
    if item_id:
        head_parts.append(item_id)
    if isinstance(score, (int, float)):
        head_parts.append(f"score={score:.3f}")
    head = " · ".join(head_parts)
    if preview:
        return f"- {head}\n  {_truncate_chars(preview, 100)}"
    return f"- {head}"


def _truncate_chars(text: str, limit: int) -> str:
    """按字符数截断，适合对长度不敏感的中间说明。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _truncate_tokens(text: str, cap: int) -> str:
    """按 token 数截断，尽量保留更完整的 JSON / 长列表工具返回内容。"""
    return truncate_tokens(text, cap)


def compact_history_for_structured(history: list[BaseMessage]) -> list[BaseMessage]:
    """将工具调用轨迹折叠成证据摘要，供之后的 ``provider.structured()`` 使用。

    保留原始 SystemMessage / HumanMessage，并把 AIMessage.tool_calls + ToolMessage 的往返
    变成新增的 HumanMessage 文本块；这样 with_structured_output 解析历史时不会撞到偏离目标
    schema 的 tool_call 名称。
    """
    system_messages: list[BaseMessage] = []
    human_messages: list[BaseMessage] = []
    trace_lines: list[str] = []
    pending_call_label: dict[str, str] = {}

    for message in history:
        if isinstance(message, SystemMessage):
            system_messages.append(message)
        elif isinstance(message, HumanMessage):
            human_messages.append(message)
        elif isinstance(message, AIMessage):
            calls = getattr(message, "tool_calls", None) or []
            for call in calls:
                pending_call_label[call["id"]] = (
                    f"{call['name']}({call.get('args', {})})"
                )
            content = (message.content or "").strip() if isinstance(message.content, str) else ""
            if content and not calls:
                trace_lines.append(
                    f"- 中间思考：{_truncate_chars(content, _MIDDLE_THOUGHT_CHAR_CAP)}"
                )
        elif isinstance(message, ToolMessage):
            label = pending_call_label.pop(message.tool_call_id, "未知调用")
            result = message.content if isinstance(message.content, str) else str(message.content)
            trace_lines.append(
                f"- 已调用 {label} -> {_truncate_tokens(result, _TOOL_RESULT_TOKEN_CAP)}"
            )

    if not trace_lines:
        return [*system_messages, *human_messages]

    digest = "\n".join(trace_lines)
    return [
        *system_messages,
        *human_messages,
        HumanMessage(
            f"【刚通过工具收集到的证据】\n{digest}\n\n"
            "请直接基于以上证据生成结构化输出，不要再调用工具。"
        ),
    ]
