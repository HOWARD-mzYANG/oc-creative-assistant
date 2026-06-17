"""灵感 agent 节点。

调用 LlmProvider 输出 InspirationOutput，并强制包含 reasoning 字段以显式给出推理。
prompt 由 build_memory_block 注入多层记忆 + RAG 上下文，让 LLM 在已有世界观和最近对话中
发散创意，不偏离用户上下文。

工具是“可选”的：LLM 自行决定是否要先用 search_nodes 检查项目里是否已有相似节点。
research_agent 强制使用工具的策略不适合头脑风暴场景；这里用 ReAct 早退出机制，让 LLM 在
没有问题时直接收束，本轮不调用任何工具也是有效路径。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import build_memory_block
from app.agents.schemas import InspirationOutput
from app.agents.state import AgentState
from app.agents.structured_call import call_structured
from app.agents.tool_loop import compact_history_for_structured, emit_trace_item, run_tool_loop
from app.agents.tools import make_project_tools
from app.agents.web_query import resolve_web_search_enabled
from app.llm.factory import get_llm_provider
from app.agents.prompts import load_prompt


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("inspiration")


def inspiration_agent_node(state: AgentState) -> dict[str, Any]:
    """可选通过 ReAct 循环核验并生成 InspirationOutput；LLM 失败时优雅降级。"""
    project_id = state.get("project_id", "")
    user_message = state.get("user_message", "").strip()

    if not user_message:
        empty = InspirationOutput(reasoning="用户消息为空，跳过推理。", suggestions=[])
        return {"inspiration_output": empty}

    initial_messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"{build_memory_block(state, 'inspiration')}\n\n"
            f"[用户问题]\n{user_message}"
        ),
    ]

    provider = get_llm_provider()
    tools = make_project_tools(
        project_id,
        include_web_search=resolve_web_search_enabled(
            user_message,
            state.get("web_search_mode", "auto"),
        ),
    )

    try:
        history = run_tool_loop(provider, initial_messages, tools)
        emit_trace_item(
            "Agent 正在思考中",
            "工具证据已收集完成，正在整理灵感建议。",
            node="inspiration_agent",
        )
        output = call_structured(
            provider,
            compact_history_for_structured(history),
            InspirationOutput,
            label="inspiration_agent",
        )
        if output is None:
            output = InspirationOutput(
                reasoning="结构化输出为空。",
                suggestions=[],
            )
    except Exception as error:  # noqa: BLE001
        logger.warning("inspiration_agent LLM call failed, degrading: %s", error)
        output = InspirationOutput(
            reasoning=f"调用失败（{type(error).__name__}）；暂时无法进行灵感发散。",
            suggestions=[],
        )
    return {"inspiration_output": output}
