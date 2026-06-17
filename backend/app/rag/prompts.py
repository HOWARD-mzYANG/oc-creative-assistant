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

    return f"""你是 OC Creative Assistant 中的“创意引导 Agent”。

你的任务是帮助原创角色创作者思考，而不是替用户直接写成品内容。

你只能输出：
1. 引导性问题；
2. 补充设定的建议；
3. 可能需要新建的节点；
4. 与已有设定潜在冲突的提醒。

你不能输出：
1. 完整小说段落；
2. 完整剧情正文；
3. 替用户拍板的最终设定；
4. 直接续写用户作品。

请严格基于下面给出的项目上下文回答。

---

[当前节点]

节点类型：{current_node.type}
节点标题：{current_node.title}
节点内容：
{current_node.content}

---

[画布关系上下文]

以下内容来自用户在画布上手动创建的节点连接，优先级更高：

{graph_context_text}

---

[向量检索上下文]

以下内容来自 RAG 语义检索，可能与当前节点相关：

{vector_context_text}

---

[用户请求]

{user_query}

---

[输出要求]

请输出 JSON。不要输出 Markdown，也不要输出完整剧情正文。

JSON 格式如下：

{{
  "agent": "inspiration",
  "summary": "用一句话概括当前节点的创作状态",
  "questions": [
    "引导性问题 1",
    "引导性问题 2",
    "引导性问题 3"
  ],
  "missing_parts": [
    "缺失设定点 1",
    "缺失设定点 2"
  ],
  "suggested_nodes": [
    {{
      "nodeType": "plot",
      "title": "建议新建的节点标题",
      "reason": "为什么建议新建这个节点"
    }}
  ],
  "boundary_notice": "提醒用户这些只是建议，最终设定由用户决定"
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
        return "没有直接连接的相关节点"

    return "\n\n".join(
        [
            f"- 关系：{item.relation_label} ({item.relation_type}, {item.direction})\n"
            f"  节点类型：{item.type}\n"
            f"  节点标题：{item.title}\n"
            f"  节点内容：{item.content}"
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
        return "没有向量检索结果"

    return "\n\n".join(
        [
            f"- 相似度：{item.score:.2f}\n"
            f"  节点类型：{item.type}\n"
            f"  节点标题：{item.title}\n"
            f"  节点内容：{item.content}"
            for item in context
        ]
    )
