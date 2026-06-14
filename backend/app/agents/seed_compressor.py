"""项目 seed compressor (first_revision stage 5).

A standalone entrypoint, 【not inside the main conversation StateGraph】: it
compresses a project's current state (all nodes, partitioned by sub-graph) into
a structured seed JSON (worldview / characters / plot / style), for the Chat
Agent to inject cheaply at startup (decision 4: seed ~500 tokens).

Called by project_service.rebuild_seed and persisted to ProjectSeedORM; trigger
sources include chat session close, workspace save debounce, and the manual
rebuild API.
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
    "You are the creative assistant's project seed compressor. Task: compress "
    "the project's current node state below into a structured snapshot, so the "
    "conversation assistant can quickly grasp the whole project at the start. "
    "Only summarize objectively; do not add new settings, do not extend the "
    "plot. worldview_summary: summarize the worldbuilding in 2-3 sentences; "
    "main_characters: list the main character names (at most 8); plot_outline: "
    "summarize the current plot direction in 2-4 sentences; style_notes: "
    "summarize the tone/style (leave empty if none)."
)


def _collect_project_brief(project_id: str) -> tuple[str, str]:
    """读取 project name + node list grouped by type, assembled into the compression input text."""
    with SessionLocal() as db:
        project = db.get(ProjectORM, project_id)
        project_name = project.name if project is not None else project_id
        nodes = read_ordered_nodes(db, project_id)

    grouped: dict[str, list[NodeORM]] = {}
    for node in nodes:
        grouped.setdefault(node.node_type, []).append(node)

    lines: list[str] = [f"Project name: {project_name}"]
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
    """Generate the project seed JSON string; return None when the project has no content or the LLM fails.

    When None is returned, the caller decides the fallback strategy
    (project_service falls back to a placeholder seed).
    """
    _, brief = _collect_project_brief(project_id)
    if brief.count("\n") <= 1:  # only the project name line → project has no content yet
        return None

    messages = [
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(f"【Project Current Nodes】\n{brief}"),
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
