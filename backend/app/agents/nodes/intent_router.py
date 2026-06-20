"""意图分类节点。

将用户最新一轮消息分类为 agent 类型，并写入 state.intent，使下游图能按意图路由到匹配的
agent。空消息会直接回退到 small_talk，不调用 LLM，以节省成本。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import format_current_nodes
from app.agents.structured_call import call_structured
from app.agents.schemas import IntentClassification
from app.agents.state import AgentState
from app.llm.factory import get_llm_provider
from app.agents.prompts import load_prompt


_SYSTEM_PROMPT = load_prompt("intent_router")

# 实质性的项目/故事问题不能被开头寒暄吞掉。
_PROJECT_QUERY_FRAGMENTS = (
    "看得到",
    "能看见",
    "看到",
    "可见",
    "故事",
    "情节",
    "剧情",
    "剧本",
    "项目里",
    "项目内",
    "画布",
    "节点",
    "写了什么",
    "有哪些",
    "can you see",
    "do you see",
    "my story",
    "my plot",
    "what plot",
    "what story",
    "what do i have",
    "what have i",
    "plot nodes",
    "story nodes",
)

# 当 LLM 对明确创作任务误判为 small_talk 或未返回结果时，用启发式覆盖。
_STRUCTURE_FRAGMENTS = (
    "create a character",
    "create character",
    "add a character",
    "new character",
    "create a plot",
    "create plot",
    "add a node",
    "add to the canvas",
    "build a relation",
    "build relation",
    " named ",
    "创建角色",
    "创建人物",
    "新建角色",
    "添加角色",
    "创建情节",
    "建立关系",
    "加到画布",
)

_INSPIRATION_FRAGMENTS = (
    "write a story",
    "i want to write",
    "help me write",
    "brainstorm",
    "what else can",
    "what else could",
    "帮我想",
    "想写",
    "写一个故事",
    "写故事",
)

_SIMULATION_FRAGMENTS = (
    "what if",
    "what would happen",
    "would happen if",
    "如果",
    "会怎样",
    "会怎么样",
)


def _looks_like_project_query(message: str) -> bool:
    """用关键词判断消息是否在询问项目或画布内容。"""
    text = message.strip().lower()
    raw = message.strip()
    return any(frag in raw or frag in text for frag in _PROJECT_QUERY_FRAGMENTS)


def _guess_intent_from_message(message: str) -> IntentClassification | None:
    """当结构化意图分类缺失或过于笼统时，使用关键词兜底。"""
    text = message.strip().lower()
    raw = message.strip()

    if any(frag in text or frag in raw for frag in _SIMULATION_FRAGMENTS):
        return IntentClassification(
            primary="simulation",
            confidence=0.8,
            reasoning="启发式检测到假设性表达。",
        )

    if any(frag in text or frag in raw for frag in _STRUCTURE_FRAGMENTS):
        return IntentClassification(
            primary="structure",
            confidence=0.85,
            reasoning="启发式检测到实体或关系创建表达。",
        )

    if any(frag in text or frag in raw for frag in _INSPIRATION_FRAGMENTS):
        return IntentClassification(
            primary="inspiration",
            confidence=0.8,
            reasoning="启发式检测到开放式故事或头脑风暴表达。",
        )

    if _looks_like_project_query(message):
        return IntentClassification(
            primary="research",
            confidence=0.85,
            reasoning="启发式检测到项目/故事可见性或内容查询。",
        )

    return None


def _coerce_substantive_intent(
    intent: IntentClassification,
    user_message: str,
) -> IntentClassification:
    """当 LLM 把明确创作请求误判为闲聊时，用启发式意图覆盖。"""
    if intent.primary != "small_talk":
        return intent
    guessed = _guess_intent_from_message(user_message)
    if guessed is None:
        return intent
    return IntentClassification(
        primary=guessed.primary,
        confidence=max(intent.confidence, guessed.confidence),
        reasoning=guessed.reasoning,
    )


def intent_router_node(state: AgentState) -> dict[str, Any]:
    """根据用户消息 + 最近对话决定 IntentClassification；空消息直接进入 small_talk。"""
    user_message = state.get("user_message", "").strip()
    if not user_message:
        return {
            "intent": IntentClassification(primary="small_talk", reasoning="用户消息为空。"),
        }

    recent = state.get("recent_messages") or []
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent[-4:])
    history_block = f"[最近对话]\n{history}\n\n" if history else ""
    quoted_block = format_current_nodes(state.get("current_nodes") or [])
    quoted_section = (
        f"[画布引用节点]\n{quoted_block}\n\n"
        if state.get("current_nodes")
        else ""
    )

    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"{history_block}{quoted_section}[最新消息]\n{user_message}"
        ),
    ]

    intent = call_structured(
        get_llm_provider(),
        messages,
        IntentClassification,
        label="intent_router",
    )

    if intent is None:
        guessed = _guess_intent_from_message(user_message)
        if guessed is not None:
            intent = guessed
        elif state.get("current_nodes"):
            intent = IntentClassification(
                primary="research",
                confidence=0.5,
                reasoning="意图分类 LLM 未返回结果；用户引用了画布节点，回退到 research。",
            )
        else:
            intent = IntentClassification(
                primary="small_talk",
                confidence=0.5,
                reasoning="意图分类 LLM 未返回结果；回退到 small_talk。",
            )
    else:
        intent = _coerce_substantive_intent(intent, user_message)

    return {"intent": intent}
