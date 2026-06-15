"""LangGraph StateGraph 组装。

把 AgentState、节点和路由规则连接成一个可执行图；在 compile 阶段绑定
SqliteSaver，使同一 thread_id 的多次调用可以继承此前保存的中间状态。

intent_router 之后有两段路由：
- 第 1 段 ``_route_after_intent``：small_talk 直接进入 chat_assembler，
  不触碰 chroma 或任何 agent；另外四类实质性意图进入完整的检索 + agent 流水线
- 第 2 段 ``_route_to_agent``：context_compress 之后，根据 intent 精确分发到匹配 agent

START → load_context → intent_router
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
           small_talk             else (4 intents)
                │                       ▼
                │              parallel_retrieval
                │                       │
                │                       ▼
                │               context_compress
                │                       │
                │             ┌─────────┼─────────┬───────────┐
                │             ▼         ▼         ▼           ▼
                │       inspiration  research  structure  simulation
                │             └─────────┴─────────┴───────────┘
                │                       │
                │                       ▼
                │                boundary_check
                │                       │
                └───────────┬───────────┘
                            ▼
                       chat_assembler
                            │
                            ▼
                      persistence_hub
                            │
                            ▼
                     summary_compress → END
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.config import get_stream_writer

from app.agents.checkpointer import get_checkpointer
from app.agents.nodes.boundary_check import boundary_check_node
from app.agents.nodes.chat_assembler import chat_assembler_node
from app.agents.nodes.context_compress import context_compress_node
from app.agents.nodes.inspiration_agent import inspiration_agent_node
from app.agents.nodes.intent_router import intent_router_node
from app.agents.nodes.load_context import load_context_node
from app.agents.nodes.parallel_retrieval import parallel_retrieval_node
from app.agents.nodes.persistence_hub import persistence_hub_node
from app.agents.nodes.question_planner import question_planner_node
from app.agents.nodes.research_agent import research_agent_node
from app.agents.nodes.simulation_agent import simulation_agent_node
from app.agents.nodes.structure_agent import structure_agent_node
from app.agents.nodes.structured_extractor import structured_extractor_node
from app.agents.nodes.summary_compress import summary_compress_node
from app.agents.progress import NODE_LABELS, NODE_RUNNING_LABELS
from app.agents.state import AgentState


logger = logging.getLogger(__name__)


_AGENT_NODE_BY_INTENT: dict[str, str] = {
    "inspiration": "inspiration_agent",
    "research": "research_agent",
    "structure": "structure_agent",
    "simulation": "simulation_agent",
}
"""这里只映射四类“实质性”意图；small_talk 已在 _route_after_intent 被拦截，
不会到达这一层路由，因此不再放入表中。"""

_AGENT_NODES: tuple[str, ...] = tuple(_AGENT_NODE_BY_INTENT.values())


AgentNode = Callable[[AgentState], dict[str, Any]]


def _safe_write_progress(
    writer: Callable[[dict[str, Any]], None] | None,
    event: dict[str, Any],
) -> None:
    if writer is None:
        return
    try:
        writer(event)
    except Exception:
        # 进度事件只是观测层；即使当前调用不是 stream 模式，也不能影响主流程。
        return


def _with_progress(node_name: str, node: AgentNode) -> AgentNode:
    """给 LangGraph 节点增加开始事件和耗时日志。"""

    def wrapped(state: AgentState) -> dict[str, Any]:
        try:
            writer = get_stream_writer()
        except Exception:
            writer = None

        _safe_write_progress(
            writer,
            {
                "type": "node_start",
                "node": node_name,
                "label": NODE_RUNNING_LABELS.get(node_name, f"正在{node_name}"),
            },
        )

        start = time.perf_counter()
        try:
            return node(state)
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            logger.info(
                "agent-timing node=%s label=%s elapsed_ms=%s",
                node_name,
                NODE_LABELS.get(node_name, node_name),
                elapsed_ms,
            )
            print(
                "[agent-timing] "
                f"node={node_name} "
                f"label={NODE_LABELS.get(node_name, node_name)} "
                f"elapsed_ms={elapsed_ms}",
                flush=True,
            )
            _safe_write_progress(
                writer,
                {
                    "type": "node_timing",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "elapsed_ms": elapsed_ms,
                },
            )

    return wrapped


def _route_after_intent(state: AgentState) -> str:
    """intent_router 之后的第一段路由：small_talk 跳过检索 / agent。

    缺失 intent 时也回退到 small_talk，因此闲聊回复在图中任何位置都不会命中
    chroma。任一路径都会先经过 question_planner（开关关闭时为空操作），
    然后进入 chat_assembler。
    """
    intent = state.get("intent")
    if intent is None or intent.primary == "small_talk":
        return "question_planner"
    return "parallel_retrieval"


def _route_to_agent(state: AgentState) -> str:
    """context_compress 之后的第二段路由：按 intent.primary 分发到具体 agent。

    到达这一层时，intent 保证是四类实质性意图之一（small_talk 已在上游拦截）；
    如果 LLM 偶尔返回新的、未注册的 primary，则回退到 inspiration_agent，
    避免图崩溃。
    """
    intent = state["intent"]
    return _AGENT_NODE_BY_INTENT.get(intent.primary, "inspiration_agent")


def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("load_context", _with_progress("load_context", load_context_node))
    builder.add_node(
        "intent_router",
        _with_progress("intent_router", intent_router_node),
    )
    builder.add_node(
        "parallel_retrieval",
        _with_progress("parallel_retrieval", parallel_retrieval_node),
    )
    builder.add_node(
        "context_compress",
        _with_progress("context_compress", context_compress_node),
    )
    builder.add_node(
        "inspiration_agent",
        _with_progress("inspiration_agent", inspiration_agent_node),
    )
    builder.add_node(
        "research_agent",
        _with_progress("research_agent", research_agent_node),
    )
    builder.add_node(
        "structure_agent",
        _with_progress("structure_agent", structure_agent_node),
    )
    builder.add_node(
        "simulation_agent",
        _with_progress("simulation_agent", simulation_agent_node),
    )
    builder.add_node(
        "boundary_check",
        _with_progress("boundary_check", boundary_check_node),
    )
    # 后台 B-agents（first_revision 决策 5）：question_planner 在组装前规划追问，
    # structured_extractor 在持久化后抽取实体；extraction_enabled 关闭时二者都是空操作。
    builder.add_node(
        "question_planner",
        _with_progress("question_planner", question_planner_node),
    )
    builder.add_node(
        "chat_assembler",
        _with_progress("chat_assembler", chat_assembler_node),
    )
    builder.add_node(
        "persistence_hub",
        _with_progress("persistence_hub", persistence_hub_node),
    )
    builder.add_node(
        "structured_extractor",
        _with_progress("structured_extractor", structured_extractor_node),
    )
    builder.add_node(
        "summary_compress",
        _with_progress("summary_compress", summary_compress_node),
    )

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "intent_router")

    # 第 1 段路由：small_talk 跳过检索 / agent，但仍会先经过 question_planner。
    builder.add_conditional_edges(
        "intent_router",
        _route_after_intent,
        {
            "question_planner": "question_planner",
            "parallel_retrieval": "parallel_retrieval",
        },
    )

    builder.add_edge("parallel_retrieval", "context_compress")

    # 第 2 段路由：四类实质性意图分别进入各自的 agent。
    builder.add_conditional_edges(
        "context_compress",
        _route_to_agent,
        {name: name for name in _AGENT_NODES},
    )

    for agent in _AGENT_NODES:
        builder.add_edge(agent, "boundary_check")

    # 实质性意图：boundary_check -> question_planner -> chat_assembler。
    builder.add_edge("boundary_check", "question_planner")
    builder.add_edge("question_planner", "chat_assembler")
    builder.add_edge("chat_assembler", "persistence_hub")
    # 持久化后在后台抽取（不阻塞已经流式返回的回复），然后压缩摘要。
    builder.add_edge("persistence_hub", "structured_extractor")
    builder.add_edge("structured_extractor", "summary_compress")
    builder.add_edge("summary_compress", END)

    return builder


@lru_cache(maxsize=1)
def get_agent_graph():
    """单例编译图，避免每次调用都重建；checkpointer 在 compile 阶段绑定。"""
    return _build_graph().compile(checkpointer=get_checkpointer())
