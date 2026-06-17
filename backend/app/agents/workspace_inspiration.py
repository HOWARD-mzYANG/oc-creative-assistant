"""轻量工作区灵感 agent（second_revision 变更 B / W5）。

这是一个独立的被动 agent：它不属于主聊天 StateGraph，也不复用
ChatWorkspace 的 question_planner。两者职责不同：question_planner 会主动推动对话，
而这个 agent 只在用户主动发送消息时被动回应。

输入：project id + 用户消息 + 引用节点 id。
输出：单个 WorkspaceInspirationOutput（type 为 search/rag/question/feedback + content），
通过 SSE 推送到前端，并按 type 分发到右侧栏的不同卡片。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import load_prompt
from app.agents.schemas import WorkspaceInspirationOutput
from app.db.database import SessionLocal
from app.db.models import NodeORM
from app.llm.factory import get_llm_provider


_SYSTEM_PROMPT = load_prompt("workspace_inspiration")


def _quoted_block(project_id: str, node_ids: list[str]) -> str:
    """把引用节点的标题和内容拼成 prompt 块；没有引用时返回占位文本。"""
    if not node_ids:
        return "(没有引用节点)"
    with SessionLocal() as db:
        lines: list[str] = []
        for node_id in node_ids:
            node = db.get(NodeORM, node_id)
            if node is None or node.project_id != project_id:
                continue
            content = (node.content or "").strip().replace("\n", " ")
            lines.append(f"- [{node.node_type}] {node.title}: {content[:160]}")
    return "\n".join(lines) or "(没有有效引用节点)"


def generate_workspace_output(
    project_id: str,
    message: str,
    quoted_node_ids: list[str],
) -> WorkspaceInspirationOutput:
    """同步生成一条工作区灵感输出；LLM 失败时降级为鼓励性反馈。"""
    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"[引用节点]\n{_quoted_block(project_id, quoted_node_ids)}\n\n"
            f"[用户消息]\n{message}"
        ),
    ]
    try:
        return get_llm_provider().structured(messages, WorkspaceInspirationOutput)
    except Exception:
        return WorkspaceInspirationOutput(
            reasoning="LLM 不可用，降级为反馈。",
            type="feedback",
            content="收到，我先帮你记下这个方向。你可以继续展开这个点子，也可以选中相关节点一起发给我。",
        )
