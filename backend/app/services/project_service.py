"""Project 应用服务（first_revision 第 1 阶段）。

负责项目 CRUD 和 seed 读取，并在创建项目时自动创建三个子图（plot / character / world）。
索引与图节点读写仍由 graph_store 处理；本模块只维护项目与子图的生命周期边界。
"""

import json
import uuid

from fastapi import HTTPException

from app.db.database import SessionLocal
from app.db.models import GraphORM, ProjectORM, ProjectSeedORM
from app.schemas import (
    ProjectCreateRequest,
    ProjectDetailPayload,
    ProjectSeedPayload,
    ProjectSummaryPayload,
    ProjectUpdateRequest,
)
from app.services.graph_repository import require_project


_SECTIONS = ("plot", "character", "world")


def _latest_seed_orm(session, project_id: str) -> ProjectSeedORM | None:
    """读取项目 seed 的最新版本；不存在时返回 None。"""
    return (
        session.query(ProjectSeedORM)
        .filter(ProjectSeedORM.project_id == project_id)
        .order_by(ProjectSeedORM.version.desc())
        .first()
    )


def _seed_to_payload(seed: ProjectSeedORM | None) -> ProjectSeedPayload | None:
    """把最新 seed ORM 记录转换为项目详情中的可选 payload。"""
    if seed is None:
        return None
    return ProjectSeedPayload(
        id=seed.id,
        project_id=seed.project_id,
        version=seed.version,
        seed_json=seed.seed_json,
        source=seed.source,
        created_at=seed.created_at,
    )


def _project_to_detail(session, project: ProjectORM) -> ProjectDetailPayload:
    """组装项目详情 payload，包含子图 ID 和最新 seed 快照。"""
    return ProjectDetailPayload(
        id=project.id,
        name=project.name,
        description=project.description,
        cover_image=project.cover_image,
        plot_graph_id=project.plot_graph_id,
        character_graph_id=project.character_graph_id,
        world_graph_id=project.world_graph_id,
        latest_seed=_seed_to_payload(_latest_seed_orm(session, project.id)),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _create_subgraphs(session, project: ProjectORM) -> None:
    """为项目创建三个子图并回填 FK（结构上与迁移回填一致）。"""
    graph_ids: dict[str, str] = {}
    for section in _SECTIONS:
        graph_id = uuid.uuid4().hex
        session.add(GraphORM(id=graph_id, project_id=project.id, section=section))
        graph_ids[section] = graph_id

    project.plot_graph_id = graph_ids["plot"]
    project.character_graph_id = graph_ids["character"]
    project.world_graph_id = graph_ids["world"]


def list_projects() -> list[ProjectSummaryPayload]:
    """列出所有项目，用于在项目库中显示为卡片。"""
    with SessionLocal() as session:
        projects = (
            session.query(ProjectORM).order_by(ProjectORM.updated_at.desc()).all()
        )
        return [
            ProjectSummaryPayload(
                id=p.id,
                name=p.name,
                description=p.description,
                cover_image=p.cover_image,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in projects
        ]


def get_project_detail(project_id: str) -> ProjectDetailPayload:
    """读取项目详情（包含三个 graph_id 和最新 seed）。"""
    with SessionLocal() as session:
        project = require_project(session, project_id)
        return _project_to_detail(session, project)


def create_project(payload: ProjectCreateRequest) -> ProjectDetailPayload:
    """创建项目并自动创建三个子图。"""
    with SessionLocal.begin() as session:
        project = ProjectORM(
            id=uuid.uuid4().hex,
            name=payload.name,
            description=payload.description,
        )
        session.add(project)
        session.flush()
        _create_subgraphs(session, project)
        session.flush()
        return _project_to_detail(session, project)


def update_project(project_id: str, payload: ProjectUpdateRequest) -> ProjectDetailPayload:
    """更新项目名称 / 描述 / 封面图（None 表示不变）。"""
    with SessionLocal.begin() as session:
        project = require_project(session, project_id)
        if payload.name is not None:
            project.name = payload.name
        if payload.description is not None:
            project.description = payload.description
        if payload.cover_image is not None:
            project.cover_image = payload.cover_image
        session.flush()
        return _project_to_detail(session, project)


def delete_project(project_id: str) -> None:
    """级联删除项目（graphs / nodes / edges / sessions / seeds 通过外键级联）。"""
    with SessionLocal.begin() as session:
        project = require_project(session, project_id)
        session.delete(project)


def get_latest_seed(project_id: str) -> ProjectSeedPayload | None:
    """读取项目当前 seed。"""
    with SessionLocal() as session:
        require_project(session, project_id)
        return _seed_to_payload(_latest_seed_orm(session, project_id))


def rebuild_seed(project_id: str) -> ProjectSeedPayload:
    """强制重建项目 seed，并自动递增版本。

    第 5 阶段：调用 seed_compressor 实际压缩项目当前状态；当项目尚无内容或 LLM 失败时，
    回退到空结构占位，确保端点始终返回 seed。
    """
    # 延迟导入，避免与 agents 包产生潜在循环依赖。
    from app.agents.seed_compressor import build_seed_json

    seed_json = build_seed_json(project_id) or json.dumps(
        {
            "worldview_summary": "",
            "main_characters": [],
            "plot_outline": "",
            "style_notes": "",
        },
        ensure_ascii=False,
    )
    with SessionLocal.begin() as session:
        require_project(session, project_id)
        latest = _latest_seed_orm(session, project_id)
        next_version = (latest.version + 1) if latest else 1
        seed = ProjectSeedORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            version=next_version,
            seed_json=seed_json,
            source="user_edit",
        )
        session.add(seed)
        session.flush()
        payload = _seed_to_payload(seed)

    if payload is None:  # pragma: no cover - for type narrowing only
        raise HTTPException(status_code=500, detail="重建 seed 失败")
    return payload
