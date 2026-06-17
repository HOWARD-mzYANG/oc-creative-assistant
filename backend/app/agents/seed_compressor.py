"""项目 seed 压缩器（first_revision 阶段 5）。

这是独立入口，【不在主对话 StateGraph 内】：它会把项目当前状态（所有节点，按子图分组）压缩成
结构化 seed JSON（worldview / characters / plot / style），供 Chat Agent 在启动时低成本注入
（决策 4：seed 约 500 tokens）。

由 project_service.rebuild_seed 调用，并持久化到 ProjectSeedORM；触发来源包括聊天会话关闭、
工作区保存防抖，以及手动 rebuild API。
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.schemas import SeedOutput
from app.db.database import SessionLocal
from app.db.models import NodeORM, ProjectORM
from app.llm.factory import get_llm_provider
from app.services.graph_mappers import db_fields_to_api
from app.services.graph_repository import read_ordered_nodes


_SYSTEM_PROMPT = (
    "你是创作助手的项目 seed 压缩器。任务：把下面的项目当前节点状态压缩成结构化快照，"
    "让对话助手在开场时能快速理解整个项目。只做客观总结；不要新增设定，不要续写剧情。"
    "worldview_summary：用 2-3 句话总结世界观；main_characters：列出主要角色名（最多 8 个）；"
    "plot_outline：用 2-4 句话总结当前剧情方向；style_notes：总结语气/风格（没有则留空）。"
)


def _collect_project_brief(project_id: str) -> tuple[str, str]:
    """读取项目名和按类型分组的节点列表，并组装成压缩输入文本。"""
    with SessionLocal() as db:
        project = db.get(ProjectORM, project_id)
        project_name = project.name if project is not None else project_id
        nodes = read_ordered_nodes(db, project_id)

    grouped: dict[str, list[NodeORM]] = {}
    for node in nodes:
        grouped.setdefault(node.node_type, []).append(node)

    lines: list[str] = [f"项目名称：{project_name}"]
    for node_type, items in grouped.items():
        lines.append(f"\n[{node_type}]")
        for node in items:
            content = (node.content or "").strip().replace("\n", " ")
            fields = db_fields_to_api(node.meta)
            field_text = "; ".join(f"{k}: {v}" for k, v in list(fields.items())[:6])
            line = f"- {node.title}: {content[:120]}"
            if field_text:
                line = f"{line} | {field_text[:120]}"
            lines.append(line)

    return project_name, "\n".join(lines)


def build_seed_json(project_id: str) -> str | None:
    """生成项目 seed JSON 字符串；当项目没有内容或 LLM 失败时返回 None。

    返回 None 时，由调用方决定兜底策略（project_service 会回退到占位 seed）。
    """
    _, brief = _collect_project_brief(project_id)
    if brief.count("\n") <= 1:  # 只有项目名称行，说明项目还没有内容。
        return None

    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(f"【项目当前节点】\n{brief}"),
    ]
    try:
        seed = get_llm_provider().structured(messages, SeedOutput)
    except Exception:
        return None

    return json.dumps(
        {
            "worldview_summary": seed.worldview_summary,
            "main_characters": seed.main_characters,
            "plot_outline": seed.plot_outline,
            "style_notes": seed.style_notes,
        },
        ensure_ascii=False,
    )
