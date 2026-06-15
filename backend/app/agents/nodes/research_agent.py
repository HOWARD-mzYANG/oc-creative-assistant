"""研究 agent 节点。

接收“研究型”意图（查询项目里已写内容、比较、总结），并在 ReAct 循环中按需调用
search_nodes / get_node / list_neighbors 收集证据，最终生成 ResearchOutput。

工具调用结果是 LLM 陈述的唯一依据；prompt 中“必须先调用工具”的约束防止 agent 绕过知识库
凭空编造，同时把“何时再次查询”的判断交还给 LLM。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.memory import build_memory_block
from app.agents.schemas import ResearchOutput
from app.agents.state import AgentState
from app.agents.tools import make_project_tools
from app.agents.web_query import (
    extract_web_sources_from_tool_history,
    merge_web_sources,
    prefetch_web_search,
    resolve_web_search_enabled,
)
from app.llm.factory import get_llm_provider
from app.agents.structured_call import call_structured
from app.agents.tool_loop import compact_history_for_structured, emit_trace_item, run_tool_loop
from app.agents.prompts import load_prompt
from datetime import datetime


logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("research")


def research_agent_node(state: AgentState) -> dict[str, Any]:
    """在 ReAct 循环中收集证据并生成 ResearchOutput；LLM 失败时降级为空摘要。"""
    project_id = state.get("project_id", "")
    user_message = state.get("user_message", "")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    web_prefetch_block = ""
    web_fallback_answer = ""
    prefetch_sources = []
    web_search_mode = state.get("web_search_mode", "auto")
    web_enabled = resolve_web_search_enabled(user_message, web_search_mode)
    if web_enabled:
        emit_trace_item(
            "外部检索预取",
            "检测到可能需要外部事实，正在预取 web_search 结果。",
            node="research_agent",
        )
        prefetched = prefetch_web_search(user_message)
        if prefetched is not None:
            web_prefetch_block = prefetched.block
            web_fallback_answer = prefetched.fallback_answer
            prefetch_sources = prefetched.sources
            emit_trace_item(
                "外部检索预取",
                f"已取得 {len(prefetch_sources)} 条网页来源。",
                node="research_agent",
            )
            logger.info(
                "research_agent prefetched web_search (mode=%s)",
                web_search_mode,
            )

    initial_messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"[运行时信息]\n当前时间：{now_str}\n"
            f"Agent 模型：由后端 OC_LLM_MODEL 配置决定（用户询问时可直接说明）\n\n"
            f"{build_memory_block(state, 'research')}\n\n"
            f"[用户问题]\n{user_message}"
            + (
                f"\n\n[预取的 web_search 结果——用于外部事实；引用 answer 字段]\n"
                f"{web_prefetch_block}"
                if web_prefetch_block
                else ""
            )
        ),
    ]

    provider = get_llm_provider()
    tools = make_project_tools(project_id, include_web_search=web_enabled)

    try:
        history = run_tool_loop(provider, initial_messages, tools)
        tool_sources = extract_web_sources_from_tool_history(history)
        web_sources = merge_web_sources(prefetch_sources, tool_sources)
        emit_trace_item(
            "整理研究结果",
            "工具证据收集完成，正在生成结构化研究摘要。",
            node="research_agent",
        )
        output = call_structured(
            provider,
            compact_history_for_structured(history),
            ResearchOutput,
            label="research_agent",
        )
        if output is None:
            if web_fallback_answer:
                output = ResearchOutput(
                    reasoning="结构化输出为空；已使用预取的 web_search。",
                    summary=web_fallback_answer,
                )
            else:
                output = ResearchOutput(
                    reasoning="结构化输出为空。",
                    summary=(
                        "这次没能整理出查询结果。你可以在输入框引用情节节点后再问，或直接说「我有哪些情节节点」。"
                        if any("\u4e00" <= c <= "\u9fff" for c in user_message)
                        else (
                            "这轮我没能整理出研究摘要。请在输入框引用剧情节点后再问，或换个说法。"
                        )
                    ),
                )
        if web_sources:
            output = output.model_copy(update={"web_sources": web_sources})
    except Exception as error:  # noqa: BLE001
        logger.warning("research_agent LLM call failed, degrading: %s", error)
        if web_fallback_answer:
            output = ResearchOutput(
                reasoning=f"调用失败（{type(error).__name__}）；已使用预取的 web_search。",
                summary=web_fallback_answer,
                web_sources=merge_web_sources(prefetch_sources),
            )
        else:
            output = ResearchOutput(
                reasoning=f"调用失败（{type(error).__name__}）。",
                summary="这次我没有找到相关内容。你可以换个问法，或稍后再试。",
            )
    return {"research_output": output}
