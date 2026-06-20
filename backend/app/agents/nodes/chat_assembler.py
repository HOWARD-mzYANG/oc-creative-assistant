"""聊天回复组装节点。

读取与当前意图匹配的 agent 结构化输出，并让 LLM 将其翻译成自然语言回复；small_talk
走单独的轻量 prompt，避免闲聊被项目上下文里的角色名污染，被误判为“伪装的用户名”。

为支持 token 级流式输出，主路径拆成两步：
  步骤 1 [流式]：chat_stream 生成纯文本 reply_text，并通过 get_stream_writer 将每个
                 token 推到 LangGraph custom stream
  步骤 2 [确定性]：从上游 agent 输出直接派生 cited_node_ids 和 staging_summary，
                 避免为了元信息再跑一轮 LLM

small_talk 文本很短，不值得额外走一轮请求，因此保留单次结构化调用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.agents.memory import build_memory_block, format_current_nodes
from app.agents.prompts import load_prompt
from app.agents.schemas import ChatAssemblerOutput
from app.agents.state import AgentState
from app.agents.structured_call import call_structured
from app.core.settings import get_llm_settings
from app.llm.factory import get_llm_provider, get_reply_llm_provider


_OUTPUT_KEY_BY_INTENT: dict[str, str] = {
    "inspiration": "inspiration_output",
    "research": "research_output",
    "structure": "structure_output",
    "simulation": "simulation_output",
}


_SMALL_TALK_PROMPT = load_prompt("chat_assembler_small_talk")
_REPLY_PROMPT = load_prompt("chat_assembler_reply")


def _hint_block(state: AgentState) -> str:
    """将 question_planner 规划的追问方向组装成提示块（开关关闭时为空）。

    这里只提供“建议方向”，供 assembler 自然织入回复，而不是逐字复制，避免回复变成机械追问。
    """
    hint = (state.get("next_question_hint") or "").strip()
    if not hint:
        return ""
    return (
        f"\n\n[建议的下一步追问方向（自然织入回复，不要逐字复制）]\n{hint}"
    )


def _build_small_talk_brief(state: AgentState) -> str:
    """只暴露世界观大纲的顶层信息，隐藏节点级和对话级具体名称，避免闲聊时 LLM 把项目角色误认为用户姓名。"""
    world_brief = (state.get("world_brief") or "").strip()
    if not world_brief:
        return "（暂无项目背景）"
    return f"[项目背景概览]\n{world_brief[:120]}"


def _assemble_small_talk(state: AgentState) -> ChatAssemblerOutput:
    """为闲聊意图生成轻量回复，避免把完整项目上下文注入闲聊 prompt。"""
    user_message = state.get("user_message", "")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    llm_model = get_llm_settings().model
    runtime_block = (
        f"[运行时信息]\n"
        f"当前时间：{now_str}\n"
        f"Agent 模型：{llm_model}\n"
    )
    messages = [
        SystemMessage(_SMALL_TALK_PROMPT),
        HumanMessage(
            f"{runtime_block}\n{_build_small_talk_brief(state)}\n\n"
            f"{format_current_nodes(state.get('current_nodes') or [])}\n\n"
            f"[用户最新消息]\n{user_message}"
            f"{_hint_block(state)}"
        ),
    ]
    output = call_structured(
        get_llm_provider(),
        messages,
        ChatAssemblerOutput,
        label="chat_assembler.small_talk",
    )
    if output is None:
        fallback = (
            "你好！我可以帮你查项目里的设定与情节、头脑风暴，或在画布上整理故事结构。"
            if any("\u4e00" <= c <= "\u9fff" for c in user_message)
            else (
                "你好！我可以帮你查项目设定、一起头脑风暴，或在画布上整理故事结构。"
            )
        )
        return ChatAssemblerOutput(
            reply_text=fallback,
        )
    return output


def _build_reply_messages(
    state: AgentState, output: Any, primary: str
) -> list[BaseMessage]:
    """把上游 agent 输出、记忆块和边界警告组装成最终回复模型消息。"""
    user_message = state.get("user_message", "")
    warnings = state.get("boundary_warnings") or []
    warning_block = (
        "\n\n[边界检查跳过的项目]\n" + "\n".join(f"- {item}" for item in warnings)
        if warnings
        else ""
    )

    return [
        SystemMessage(_REPLY_PROMPT),
        HumanMessage(
            f"{build_memory_block(state, primary)}\n\n"
            f"[用户最新消息]\n{user_message}\n\n"
            f"[主要意图]\n{primary}\n\n"
            f"[Agent 结构化输出]\n{output.model_dump_json()}"
            f"{warning_block}"
            f"{_hint_block(state)}\n\n"
            "请直接输出面向用户的最终回复正文；注意不要重复【最近对话】中已经说过的内容，"
            "让回复保持连续。"
        ),
    ]


def _stream_reply(messages: list[BaseMessage]) -> str:
    """流式产出 token，同时推送到 LangGraph custom stream，并返回组装后的完整文本。

    get_stream_writer 在非流式调用（例如直接 graph.invoke）下会抛 RuntimeError，因此用
    try/except 包住，让单元测试和旧接口仍可复用该节点。
    """
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None

    chunks: list[str] = []
    for chunk in get_reply_llm_provider().chat_stream_chunks(messages):
        if writer is not None:
            try:
                if chunk.reasoning:
                    writer({"type": "reasoning_token", "text": chunk.reasoning})
                if chunk.text:
                    writer({"type": "reply_token", "text": chunk.text})
            except Exception:
                writer = None
        if chunk.text:
            chunks.append(chunk.text)
    return "".join(chunks)


def _dedupe_node_ids(values: list[Any]) -> list[str]:
    """保持原顺序去重，只保留非空字符串 node_id。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        node_id = value.strip() if isinstance(value, str) else ""
        if not node_id or node_id in seen:
            continue
        result.append(node_id)
        seen.add(node_id)
    return result


def _derive_cited_node_ids(output: Any) -> list[str]:
    """从上游 agent 的显式引用字段派生引用节点，替代额外 LLM 元信息整理。"""
    values: list[Any] = list(getattr(output, "referenced_node_ids", []) or [])
    for branch in getattr(output, "branches", []) or []:
        values.extend(getattr(branch, "affected_node_ids", []) or [])
    return _dedupe_node_ids(values)


def _has_chinese(text: str) -> bool:
    """判断文本中是否包含中文字符，用于选择本地化的降级文案。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _derive_staging_summary(state: AgentState, output: Any) -> str:
    """根据 proposed_changes 数量生成短摘要，不再调用模型二次判断。"""
    changes = list(getattr(output, "proposed_changes", []) or [])
    count = len(changes)
    if count == 0:
        return ""

    is_zh = _has_chinese(state.get("user_message", ""))
    if state.get("auto_apply_staging"):
        if is_zh:
            return f"已应用 {count} 条画布变更，可在卡片中查看或调整。"
        noun = "change" if count == 1 else "changes"
        return f"Applied {count} canvas {noun}; review them in the cards."

    if is_zh:
        return f"已生成 {count} 条待确认变更。"
    noun = "change" if count == 1 else "changes"
    return f"Prepared {count} pending canvas {noun}."


def chat_assembler_node(state: AgentState) -> dict[str, Any]:
    """根据识别到的意图选择回复组装路径，并返回 LangGraph 节点输出。

    参数：
        state: 当前 agent 图状态，包含意图、上游结构化结果、记忆上下文和流式配置。

    返回：
        带 `assembler_output` 的状态增量，供后续持久化和 API 流式输出使用。
    """
    intent = state.get("intent")
    primary = intent.primary if intent is not None else ""

    if primary == "small_talk":
        return {"assembler_output": _assemble_small_talk(state)}

    output_key = _OUTPUT_KEY_BY_INTENT.get(primary)
    output = state.get(output_key) if output_key else None
    if output is None:
        return {
            "assembler_output": ChatAssemblerOutput(
                reply_text="这轮我没有得到合适的结果。可以再多告诉我一点你想要的方向吗？"
            ),
        }

    reply_text = _stream_reply(_build_reply_messages(state, output, primary))

    web_sources = []
    if primary == "research":
        research = state.get("research_output")
        if research is not None:
            web_sources = list(research.web_sources)

    return {
        "assembler_output": ChatAssemblerOutput(
            reply_text=reply_text,
            cited_node_ids=_derive_cited_node_ids(output),
            staging_summary=_derive_staging_summary(state, output),
            web_sources=web_sources,
        )
    }
