"""Question planner node (Agent B part two, first_revision decision 5).

Runs before chat_assembler: based on the seed / recent conversation / fields to
fill, it plans the direction the chat assistant should naturally follow up on
next and writes it to ``state.next_question_hint`` for the assembler to weave
into the reply.

Works only when ``extraction_enabled`` is true (ChatWorkspace full-screen chat
mode); when off it is a direct no-op, guaranteeing the FloatingChatDock legacy
flow's behavior and cost are completely unchanged.
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
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent[-6:]) or "(none)"
    deferred = state.get("deferred_fields") or []
    deferred_block = (
        "\n".join(f"- {d.get('entity')}: {d.get('field')}" for d in deferred) or "(none)"
    )
    seed = (state.get("seed_context") or state.get("world_brief") or "").strip()
    quoted_block = format_current_nodes(state.get("current_nodes") or [])

    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"[项目 seed/background]\n{seed[:500] or '(none yet)'}\n\n"
            f"[Quoted nodes from canvas]\n{quoted_block}\n\n"
            f"[Recent conversation]\n{history}\n\n"
            f"[Fields to fill]\n{deferred_block}\n\n"
            f"[User's latest message]\n{state.get('user_message', '')}"
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
