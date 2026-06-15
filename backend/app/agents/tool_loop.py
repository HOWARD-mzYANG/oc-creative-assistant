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

import tiktoken
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.core.settings import get_llm_settings
from app.llm.provider import LlmProvider, extract_provider_reasoning


MAX_TOOL_LOOPS = 3
MAX_CALLS_PER_BATCH = 3
MAX_TOTAL_TOOL_CALLS = 5
_TOOL_RESULT_TOKEN_CAP = 600
_MIDDLE_THOUGHT_CHAR_CAP = 400

# 复用与 context_compress 相同的 encoding；可离线工作，并与主流 OpenAI 兼容模型一致。
_encoder = tiktoken.get_encoding("cl100k_base")


def run_tool_loop(
    provider: LlmProvider,
    initial_messages: list[BaseMessage],
    tools: list[BaseTool],
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

    for _ in range(MAX_TOOL_LOOPS):
        response = provider.chat_with_tools(history, tools)
        if stream_reasoning:
            _emit_provider_reasoning(writer, response)
        history.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return history

        for idx, call in enumerate(tool_calls):
            within_batch = idx < MAX_CALLS_PER_BATCH
            within_budget = total_calls < MAX_TOTAL_TOOL_CALLS
            if not within_batch or not within_budget:
                content = (
                    "[已跳过：本轮工具调用超出预算"
                    f"（每轮最多 {MAX_CALLS_PER_BATCH} 次，总预算 {MAX_TOTAL_TOOL_CALLS} 次）。"
                    "请直接基于已有证据收束，不要再调用工具。]"
                )
            else:
                tool_fn = tool_by_name.get(call["name"])
                if tool_fn is None:
                    content = f"未知工具：{call['name']}"
                else:
                    try:
                        content = tool_fn.invoke(call["args"])
                    except Exception as exc:  # noqa: BLE001
                        content = f"工具执行失败：{exc}"
                total_calls += 1
            history.append(ToolMessage(content=str(content), tool_call_id=call["id"]))

        if total_calls >= MAX_TOTAL_TOOL_CALLS:
            return history

    return history


def _get_optional_stream_writer():
    try:
        return get_stream_writer()
    except Exception:
        return None


def _emit_provider_reasoning(writer, response: AIMessage) -> None:
    if writer is None:
        return
    reasoning = extract_provider_reasoning(response)
    if not reasoning:
        return
    try:
        writer({"type": "reasoning_token", "text": reasoning})
    except Exception:
        pass


def _truncate_chars(text: str, limit: int) -> str:
    """按字符数截断，适合对长度不敏感的中间说明。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _truncate_tokens(text: str, cap: int) -> str:
    """按 token 数截断，尽量保留更完整的 JSON / 长列表工具返回内容。"""
    stripped = text.strip()
    tokens = _encoder.encode(stripped)
    if len(tokens) <= cap:
        return stripped
    return _encoder.decode(tokens[:cap]) + "..."


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
