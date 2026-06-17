"""结构 agent 节点。

接收“构建结构”意图（新增节点、批量创建关系、整理角色组等）。它会在 ReAct 循环中先查重，
再提出建议，并将 StructureOutput.proposed_changes 输出到暂存区供用户确认。

当同批次的 create_edge 引用尚未持久化的新节点时，会使用 pending_id；持久化时由
canvas_apply 将 pending_id 转换为真实 node_id，从而解决“先节点后边”的依赖。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import build_memory_block
from app.agents.schemas import StructureOutput
from app.agents.state import AgentState
from app.agents.tools import make_project_tools
from app.agents.web_query import resolve_web_search_enabled
from app.llm.factory import get_llm_provider
from app.agents.structured_call import call_structured
from app.agents.tool_loop import compact_history_for_structured, emit_trace_item, run_tool_loop
from app.agents.prompts import load_prompt


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("structure")

def structure_agent_node(state: AgentState) -> dict[str, Any]:
    """在 ReAct 循环中查重并提出结构变更；LLM 失败时降级为空 proposed_changes。"""
    project_id = state.get("project_id", "")
    user_message = state.get("user_message", "")

    initial_messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"{build_memory_block(state, 'structure')}\n\n"
            f"[用户请求]\n{user_message}"
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
            "工具证据已收集完成，正在整理结构化画布变更。",
            node="structure_agent",
        )
        output = call_structured(
            provider,
            compact_history_for_structured(history),
            StructureOutput,
            label="structure_agent",
        )
        if output is None:
            output = StructureOutput(
                reasoning="结构化输出为空。",
                summary=(
                    "这次我没能整理出结构建议。你可以换个说法，或稍后再试。"
                ),
            )
    except Exception as error:  # noqa: BLE001
        logger.warning("structure_agent LLM call failed, degrading: %s", error)
        output = StructureOutput(
            reasoning=f"调用失败（{type(error).__name__}）。",
            summary="这次我没能整理出结构建议。你可以换个说法，或稍后再试。",
        )
    return {"structure_output": output}
