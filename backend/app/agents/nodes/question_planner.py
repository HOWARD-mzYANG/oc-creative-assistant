"""追问规划节点（Agent B 第二部分，first_revision 决策 5）。

在 chat_assembler 之前运行：根据 seed、最近对话和待补字段，规划聊天助手下一步应该自然追问的
方向，并写入 ``state.next_question_hint``，供 assembler 编织进回复。

仅在 ``extraction_enabled`` 为 true 时工作（ChatWorkspace 全屏聊天模式）；关闭时直接空操作，
保证 FloatingChatDock 旧流程的行为和成本完全不变。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import format_current_nodes
from app.agents.prompts import load_prompt
from app.agents.structured_call import call_structured
from app.agents.schemas import QuestionPlannerOutput
from app.agents.state import AgentState
from app.llm.factory import get_llm_provider


_SYSTEM_PROMPT = load_prompt("question_planner")


def question_planner_node(state: AgentState) -> dict[str, Any]:
    if not state.get("extraction_enabled"):
        return {}

    recent = state.get("recent_messages") or []
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent[-6:]) or "（无）"
    deferred = state.get("deferred_fields") or []
    deferred_block = (
        "\n".join(f"- {d.get('entity')}: {d.get('field')}" for d in deferred) or "（无）"
    )
    seed = (state.get("seed_context") or state.get("world_brief") or "").strip()
    quoted_block = format_current_nodes(state.get("current_nodes") or [])

    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"[项目 seed / 背景]\n{seed[:500] or '（暂无）'}\n\n"
            f"[画布引用节点]\n{quoted_block}\n\n"
            f"[最近对话]\n{history}\n\n"
            f"[待补字段]\n{deferred_block}\n\n"
            f"[用户最新消息]\n{state.get('user_message', '')}"
        ),
    ]

    out = call_structured(
        get_llm_provider(),
        messages,
        QuestionPlannerOutput,
        label="question_planner",
    )
    if out is None:
        return {}

    return {
        "next_question_hint": out.next_question,
        "question_planner_reasoning": out.reasoning,
    }
