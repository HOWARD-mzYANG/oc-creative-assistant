"""聊天回复组装节点。

读取与当前意图匹配的 agent 结构化输出，并让 LLM 将其翻译成自然语言回复；small_talk
走单独的轻量 prompt，避免闲聊被项目上下文里的角色名污染，被误判为“伪装的用户名”。

为支持 token 级流式输出，主路径拆成两步：
  步骤 1 [流式]：chat_stream 生成纯文本 reply_text，并通过 get_stream_writer 将每个
                 token 推到 LangGraph custom stream
  步骤 2 [非流式]：结构化调用从已生成的 reply_text 中提取 cited_node_ids 和
                  staging_summary

small_talk 文本很短，不值得额外走一轮请求，因此保留单次结构化调用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.agents.memory import build_memory_block, format_current_nodes
from app.agents.prompts import load_prompt
from app.agents.schemas import ChatAssemblerOutput, ChatMetadataOutput
from app.agents.state import AgentState
from app.agents.structured_call import call_structured
from app.core.settings import get_llm_settings
from app.llm.factory import get_llm_provider


_OUTPUT_KEY_BY_INTENT: dict[str, str] = {
    "inspiration": "inspiration_output",
    "research": "research_output",
    "structure": "structure_output",
    "simulation": "simulation_output",
}


_SMALL_TALK_PROMPT = load_prompt("chat_assembler_small_talk")
_REPLY_PROMPT = load_prompt("chat_assembler_reply")
_METADATA_PROMPT = load_prompt("chat_assembler_metadata")


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
            "请直接输出面向用户的最终回复正文；注意不要重复 [Recent conversation] 中已经说过的内容，"
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
    for token in get_llm_provider().chat_stream(messages):
        chunks.append(token)
        if writer is not None:
            try:
                writer({"type": "reply_token", "text": token})
            except Exception:
                writer = None
    return "".join(chunks)


def _build_meta_messages(output: Any, reply_text: str) -> list[BaseMessage]:
    return [
        SystemMessage(_METADATA_PROMPT),
        HumanMessage(
            f"[生成的回复]\n{reply_text}\n\n"
            f"[原始 agent 输出]\n{output.model_dump_json()}"
        ),
    ]


def chat_assembler_node(state: AgentState) -> dict[str, Any]:
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

    metadata = call_structured(
        get_llm_provider(),
        _build_meta_messages(output, reply_text),
        ChatMetadataOutput,
        label="chat_assembler.metadata",
    )
    if metadata is None:
        metadata = ChatMetadataOutput(cited_node_ids=[], staging_summary="")

    web_sources = []
    if primary == "research":
        research = state.get("research_output")
        if research is not None:
            web_sources = list(research.web_sources)

    return {
        "assembler_output": ChatAssemblerOutput(
            reply_text=reply_text,
            cited_node_ids=metadata.cited_node_ids,
            staging_summary=metadata.staging_summary,
            web_sources=web_sources,
        )
    }
