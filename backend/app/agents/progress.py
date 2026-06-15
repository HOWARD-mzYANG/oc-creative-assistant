"""Agent 执行进度标签。

这些标签同时给 SSE 前端展示和后端节点计时使用，集中维护可以避免
“前端显示的阶段”和“后端日志里的阶段”不一致。
"""

NODE_LABELS: dict[str, str] = {
    "load_context": "加载上下文",
    "intent_router": "判断意图",
    "parallel_retrieval": "检索知识库",
    "context_compress": "压缩上下文",
    "inspiration_agent": "发散创意",
    "research_agent": "研究与核查",
    "structure_agent": "整理结构",
    "simulation_agent": "模拟分支",
    "boundary_check": "边界检查",
    "chat_assembler": "生成回复",
    "persistence_hub": "持久化结果",
    "structured_extractor": "提取实体",
    "question_planner": "规划追问",
    "summary_compress": "压缩对话摘要",
}

NODE_RUNNING_LABELS: dict[str, str] = {
    node: f"正在{label}" for node, label in NODE_LABELS.items()
}

