"""模拟 agent 节点。

接收“如果……会怎样”这类假设性意图。在 ReAct 循环中，它会先用 search_nodes 锁定相关节点，
锚定“当前状态”，再生成 2-3 个不同走向并输出 SimulationOutput。该模式不会产生
proposed_changes；当用户选定某个分支后，下一轮自然会切到 structure 模式继续落地。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import build_memory_block
from app.agents.schemas import SimulationOutput
from app.agents.state import AgentState
from app.agents.structured_call import call_structured
from app.agents.tool_loop import compact_history_for_structured, emit_trace_item, run_tool_loop
from app.agents.tools import make_project_tools
from app.agents.web_query import resolve_web_search_enabled
from app.llm.factory import get_llm_provider
from app.agents.prompts import load_prompt


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("simulation")


def simulation_agent_node(state: AgentState) -> dict[str, Any]:
    """在 ReAct 循环中锚定当前状态并模拟分支；LLM 失败时降级为空分支。"""
    project_id = state.get("project_id", "")
    user_message = state.get("user_message", "")

    initial_messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(f"{build_memory_block(state, 'simulation')}\n\n[用户假设]\n{user_message}"),
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
            "工具证据已收集完成，正在推演剧情分支。",
            node="simulation_agent",
        )
        output = call_structured(
            provider,
            compact_history_for_structured(history),
            SimulationOutput,
            label="simulation_agent",
        )
        if output is None:
            output = SimulationOutput(
                reasoning="结构化输出为空。",
                branches=[],
            )
    except Exception as error:  # noqa: BLE001
        logger.warning("simulation_agent LLM 调用失败，降级处理：%s", error)
        output = SimulationOutput(
            reasoning=f"调用失败（{type(error).__name__}），暂时无法模拟分支。",
            branches=[],
        )
    return {"simulation_output": output}
