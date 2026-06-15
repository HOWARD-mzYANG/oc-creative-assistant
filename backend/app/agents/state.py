"""LangGraph 共享状态定义。

agent 图围绕 ``AgentState`` 流转：load_context 写入项目与会话快照，intent_router 决定本轮
意图，RAG 与对应 agent 把结果写入各自字段，assembler 和 persistence hub 再按意图取匹配
agent 的输出做后处理。

所有字段都使用 ``total=False``，因此本地测试可以只构造关心的字段子集来启动单个节点。
"""

from __future__ import annotations

from typing import TypedDict

from app.agents.schemas import (
    ChatAssemblerOutput,
    InspirationOutput,
    IntentClassification,
    ResearchOutput,
    SimulationOutput,
    StructureOutput,
)
from app.schemas import (
    RagCurrentNodePayload,
    RagGraphContextItem,
    RagMergedContextItem,
    RagVectorContextItem,
)


class AgentState(TypedDict, total=False):
    """LangGraph 节点之间共享的状态字典。"""

    session_id: str
    project_id: str
    user_message: str
    selected_node_ids: list[str]
    preferred_intent: str

    world_brief: str
    conversation_summary: str
    key_facts: list[str]
    recent_messages: list[dict]

    intent: IntentClassification

    current_nodes: list[RagCurrentNodePayload]
    graph_context: list[RagGraphContextItem]
    vector_context: list[RagVectorContextItem]
    merged_context: list[RagMergedContextItem]

    inspiration_output: InspirationOutput
    research_output: ResearchOutput
    structure_output: StructureOutput
    simulation_output: SimulationOutput

    assembler_output: ChatAssemblerOutput

    boundary_warnings: list[str]

    assistant_message_id: str
    staging_batch_id: str | None
    staging_count: int

    # first_revision 第 4 阶段：后台 B-agents（structured_extractor / question_planner）。
    # extraction_enabled 关闭时，两个节点全程都是空操作，不影响 FloatingChatDock 旧流程。
    extraction_enabled: bool
    auto_apply_staging: bool
    web_search_mode: str
    seed_context: str
    next_question_hint: str
    question_planner_reasoning: str
    deferred_fields: list[dict]
    extraction_batch_id: str | None
    extraction_count: int
    extraction_reasoning: str
    extraction_applied: list[dict]
