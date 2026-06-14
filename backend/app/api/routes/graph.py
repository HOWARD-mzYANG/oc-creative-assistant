"""图谱 HTTP 路由。

路由层只负责 HTTP 映射和响应模型声明；业务校验、持久化与索引同步都委托给服务层。
"""

from fastapi import APIRouter

from app.schemas import (
    EdgePayload,
    GraphPayload,
    MemorySearchRequest,
    MemorySearchResponse,
    NodePayload,
    ProjectPayload,
    SaveGraphRequest,
    UpdateNodeRequest,
)
from app.services.graph_store import (
    create_edge,
    create_node,
    delete_node,
    ensure_default_project,
    get_project_graph,
    get_subgraph,
    save_project_graph,
    save_subgraph,
    update_node,
)
from app.services.rag_service import search_project_memory


router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/projects/default", response_model=ProjectPayload)
async def read_default_project() -> ProjectPayload:
    """返回默认项目；首次调用会自动创建项目和示例图谱。"""
    return ensure_default_project()


@router.get("/graphs/{graph_id}", response_model=GraphPayload)
async def read_subgraph(graph_id: str) -> GraphPayload:
    """读取单个子图快照（first_revision 决策 1）。

    与按项目维度的 ``/projects/{id}/graph`` 共存：旧的单画布工作区继续使用项目维度，
    新的三视图工作区则按 graph_id 分别加载 plot / character / world。
    """
    return get_subgraph(graph_id)


@router.put("/graphs/{graph_id}", response_model=GraphPayload)
async def replace_subgraph_route(graph_id: str, payload: SaveGraphRequest) -> GraphPayload:
    """保存单个子图快照，整体替换该子图的节点和内部边。"""
    return save_subgraph(graph_id, payload)


@router.get("/projects/{project_id}/graph", response_model=GraphPayload)
async def read_project_graph(project_id: str) -> GraphPayload:
    """读取指定项目下的完整图谱快照。"""
    return get_project_graph(project_id)


@router.put("/projects/{project_id}/graph", response_model=GraphPayload)
async def replace_project_graph(project_id: str, payload: SaveGraphRequest) -> GraphPayload:
    """保存当前画布快照，整体替换项目图谱。"""
    return save_project_graph(project_id, payload)


@router.post("/projects/{project_id}/memory/search", response_model=MemorySearchResponse)
async def search_memory(project_id: str, payload: MemorySearchRequest) -> MemorySearchResponse:
    """在指定项目内执行 Lore Memory 语义搜索。"""
    return search_project_memory(project_id, payload)


@router.post("/projects/{project_id}/nodes", response_model=NodePayload)
async def add_node(project_id: str, payload: NodePayload) -> NodePayload:
    """创建或覆盖单个节点，预留给后续细粒度保存。"""
    return create_node(project_id, payload)


@router.patch("/projects/{project_id}/nodes/{node_id}", response_model=NodePayload)
async def patch_node(project_id: str, node_id: str, payload: UpdateNodeRequest) -> NodePayload:
    """更新节点基础字段或位置。"""
    return update_node(project_id, node_id, payload)


@router.delete("/projects/{project_id}/nodes/{node_id}", status_code=204)
async def remove_node(project_id: str, node_id: str) -> None:
    """删除单个节点及相关边（供聊天行内卡片的“撤销/拒绝”使用）。"""
    delete_node(project_id, node_id)


@router.post("/projects/{project_id}/edges", response_model=EdgePayload)
async def add_edge(project_id: str, payload: EdgePayload) -> EdgePayload:
    """创建或覆盖单条边，并校验两个端点节点属于同一项目。"""
    return create_edge(project_id, payload)
