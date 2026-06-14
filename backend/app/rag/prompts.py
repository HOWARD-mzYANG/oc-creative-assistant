"""RAG prompt 模板与上下文格式化。

本模块只负责将已过滤的图谱/向量上下文组装成 Agent 预览 prompt。它不读取数据库，也不触发
真实 LLM 调用。
"""

from __future__ import annotations

from app.schemas import RagCurrentNodePayload, RagGraphContextItem, RagVectorContextItem


def build_inspiration_prompt(
    current_node: RagCurrentNodePayload,
    graph_context: list[RagGraphContextItem],
    vector_context: list[RagVectorContextItem],
    user_query: str,
) -> str:
    """构建 Idea-guidance Agent 的 prompt。

    参数：
        current_node: 当前请求 AI 辅助的节点。
        graph_context: 从画布边提取的一跳关系上下文。
        vector_context: 从向量索引检索到的语义相关节点。
        user_query: 用户输入的检索问题，或服务层生成的兜底问题。

    返回：
        用于前端预览的 prompt 文本；本函数不调用 LLM。
    """
    graph_context_text = _format_graph_context(graph_context)
    vector_context_text = _format_vector_context(vector_context)

    return f"""You are the "Idea-guidance Agent" in OC Creative Assistant.

Your task is to help original-character creators think, not to write the actual content for the user.

You may only output:
1. Guiding questions;
2. Suggestions for supplementing settings;
3. New nodes that may need to be created;
4. Reminders about potential conflicts with existing settings.

You may not output:
1. Complete novel passages;
2. Complete plot prose;
3. Final settings decided on the user's behalf;
4. Direct continuation of the user's work.

Please answer strictly based on the project context provided below.

---

[Current Node]

Node type: {current_node.type}
Node title: {current_node.title}
Node content:
{current_node.content}

---

[Canvas Relation Context]

The following comes from node connections the user manually created on the canvas, and has higher priority:

{graph_context_text}

---

[Vector Retrieval Context]

The following comes from RAG semantic retrieval and may be related to the current node:

{vector_context_text}

---

[User Request]

{user_query}

---

[Output Requirements]

Please output JSON. Do not output Markdown, and do not output complete plot prose.

The JSON format is as follows:

{{
  "agent": "inspiration",
  "summary": "A one-sentence summary of the creative state of the current node",
  "questions": [
    "Guiding question 1",
    "Guiding question 2",
    "Guiding question 3"
  ],
  "missing_parts": [
    "Missing setting point 1",
    "Missing setting point 2"
  ],
  "suggested_nodes": [
    {{
      "nodeType": "plot",
      "title": "Suggested new node title",
      "reason": "Why this node is suggested"
    }}
  ],
  "boundary_notice": "Remind the user that these are only suggestions and that the final settings are decided by the user"
}}"""


def _format_graph_context(context: list[RagGraphContextItem]) -> str:
    """格式化图关系上下文。

    参数：
        context: 已过滤的一跳图关系上下文。

    返回：
        prompt 中的图关系上下文片段。
    """
    if not context:
        # 显式写“无”比空字符串更能帮助下游 LLM 理解上下文缺口。
        return "No directly connected related nodes"

    return "\n\n".join(
        [
            f"- Relation: {item.relation_label} ({item.relation_type}, {item.direction})\n"
            f"  Node type: {item.type}\n"
            f"  Node title: {item.title}\n"
            f"  Node content: {item.content}"
            for item in context
        ]
    )


def _format_vector_context(context: list[RagVectorContextItem]) -> str:
    """格式化向量检索上下文。

    参数：
        context: 已过滤的向量检索结果。

    返回：
        prompt 中的向量检索上下文片段。
    """
    if not context:
        # 即使没有结果也保留占位段落，方便前端调试 prompt 结构。
        return "No vector retrieval results"

    return "\n\n".join(
        [
            f"- Similarity: {item.score:.2f}\n"
            f"  Node type: {item.type}\n"
            f"  Node title: {item.title}\n"
            f"  Node content: {item.content}"
            for item in context
        ]
    )
