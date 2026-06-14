"""项目 HTTP 路由（first_revision 第 1 阶段）。

项目 CRUD 以及 seed 读取 / 重建。路由层只负责 HTTP 映射；生命周期与子图创建委托给
project_service。
"""

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas import (
    AgentStagingBatchPayload,
    CrossReferenceResponse,
    NodeFieldsPayload,
    ProjectCreateRequest,
    ProjectDetailPayload,
    ProjectSeedPayload,
    ProjectSummaryPayload,
    ProjectUpdateRequest,
    WorkspaceChatRequest,
)
from app.services.chat_service import list_project_staging
from app.services.cross_reference_service import get_node_cross_references
from app.services.node_fields_service import get_node_fields, set_node_fields
from app.services.workspace_chat_service import stream_workspace_chat
from app.services.project_service import (
    create_project,
    delete_project,
    get_latest_seed,
    get_project_detail,
    list_projects,
    rebuild_seed,
    update_project,
)
from app.services.project_io import export_project_oc, import_project_oc

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummaryPayload])
async def read_projects() -> list[ProjectSummaryPayload]:
    """列出所有项目（项目库卡片）。"""
    return list_projects()


@router.post("", response_model=ProjectDetailPayload)
async def add_project(payload: ProjectCreateRequest) -> ProjectDetailPayload:
    """创建项目，并自动创建三个子图。"""
    return create_project(payload)


@router.get("/{project_id}", response_model=ProjectDetailPayload)
async def read_project(project_id: str) -> ProjectDetailPayload:
    """项目详情（包含三个 graph_id 和最新 seed）。"""
    return get_project_detail(project_id)


@router.patch("/{project_id}", response_model=ProjectDetailPayload)
async def patch_project(project_id: str, payload: ProjectUpdateRequest) -> ProjectDetailPayload:
    """更新项目名称 / 描述（用于项目概览页编辑简介）。"""
    return update_project(project_id, payload)


@router.delete("/{project_id}", status_code=204)
async def remove_project(project_id: str) -> None:
    """级联删除项目。"""
    delete_project(project_id)


@router.get("/{project_id}/export.oc")
async def export_project_oc_route(project_id: str) -> dict:
    """导出项目的无损 .oc 快照（三个看板全部包含）。"""
    try:
        return export_project_oc(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/import.oc", response_model=ProjectDetailPayload)
async def import_project_oc_route(file: UploadFile = File(...)) -> ProjectDetailPayload:
    """将 .oc 快照导入为新项目；返回新建项目详情。"""
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"无效的 .oc 文件：{exc}")
    try:
        project_id = import_project_oc(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return get_project_detail(project_id)

    
@router.get("/{project_id}/staging", response_model=list[AgentStagingBatchPayload])
async def read_project_staging(
    project_id: str, status: str | None = "pending"
) -> list[AgentStagingBatchPayload]:
    """按项目列出暂存项（默认仅 pending），供 ChatWorkspace 实时显示后台提取出的实体。"""
    return list_project_staging(project_id, status)


@router.get("/{project_id}/nodes/{node_id}/fields", response_model=NodeFieldsPayload)
async def read_node_fields(project_id: str, node_id: str) -> NodeFieldsPayload:
    """读取角色卡的自由表单字段。"""
    return get_node_fields(project_id, node_id)


@router.put("/{project_id}/nodes/{node_id}/fields", response_model=NodeFieldsPayload)
async def replace_node_fields(
    project_id: str, node_id: str, payload: NodeFieldsPayload
) -> NodeFieldsPayload:
    """整体替换角色卡自由表单字段，并持久化到 node.meta JSON。"""
    return set_node_fields(project_id, node_id, payload.fields)


@router.post("/{project_id}/workspace_chat")
async def workspace_chat(project_id: str, payload: WorkspaceChatRequest) -> StreamingResponse:
    """工作区底部聊天框：被动 Inspiration agent 的 SSE 流（W5）。"""
    return StreamingResponse(
        stream_workspace_chat(project_id, payload.message, payload.quoted_node_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{project_id}/nodes/{node_id}/cross_references",
    response_model=CrossReferenceResponse,
)
async def read_node_cross_references(
    project_id: str, node_id: str
) -> CrossReferenceResponse:
    """返回该节点在其他子图中的引用位置（供角色卡反向引用区域使用）。"""
    return get_node_cross_references(project_id, node_id)


@router.get("/{project_id}/seed", response_model=ProjectSeedPayload)
async def read_project_seed(project_id: str) -> ProjectSeedPayload:
    """读取项目当前 seed；尚无 seed 时返回 404。"""
    seed = get_latest_seed(project_id)
    if seed is None:
        raise HTTPException(status_code=404, detail="未找到 Seed")
    return seed


@router.post("/{project_id}/seed/rebuild", response_model=ProjectSeedPayload)
async def rebuild_project_seed(project_id: str) -> ProjectSeedPayload:
    """强制重建项目 seed，并递增版本（第 1 阶段占位，第 5 阶段接入压缩器）。"""
    return rebuild_seed(project_id)
