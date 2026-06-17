"""后端 API 使用的 Pydantic DTO。

字段命名遵循现有前端契约，避免结构迁移改变 HTTP 请求和响应格式。
内部数据库字段与 API 字段之间的转换由服务层处理。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectPayload(BaseModel):
    """项目的最小展示信息。"""

    id: str
    name: str


class ProjectSeedPayload(BaseModel):
    """项目 seed DTO（first_revision 决策 3）。"""

    id: str
    project_id: str
    version: int
    seed_json: str = ""
    source: str = "user_edit"
    created_at: datetime | None = None


class GraphInfoPayload(BaseModel):
    """子图元数据 DTO。"""

    id: str
    project_id: str
    section: Literal["plot", "character", "world"]


class ProjectSummaryPayload(BaseModel):
    """项目库卡片所需的概览信息。"""

    id: str
    name: str
    description: str = ""
    cover_image: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectDetailPayload(BaseModel):
    """项目详情：包含三个子图 ID 和最新 seed（first_revision 第 1 阶段）。"""

    id: str
    name: str
    description: str = ""
    cover_image: str = ""
    plot_graph_id: str | None = None
    character_graph_id: str | None = None
    world_graph_id: str | None = None
    latest_seed: ProjectSeedPayload | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectCreateRequest(BaseModel):
    """创建项目请求体；后端会自动创建三个子图。"""

    name: str
    description: str = ""


class ProjectUpdateRequest(BaseModel):
    """项目局部更新请求体；None 表示不修改该字段。"""

    name: str | None = None
    description: str | None = None
    cover_image: str | None = None


class NodeFieldsPayload(BaseModel):
    """节点自由表单字段 DTO（first_revision 决策 2）。"""

    node_id: str
    fields: dict[str, str] = Field(default_factory=dict)


class WorkspaceChatRequest(BaseModel):
    """工作区底部聊天框请求体（second_revision 变更 B / W5）。"""

    message: str = ""
    quoted_node_ids: list[str] = Field(default_factory=list)


class CrossReferenceItem(BaseModel):
    """单条跨子图引用（first_revision 第 6 阶段）。"""

    edge_id: str
    other_node_id: str
    other_title: str
    other_section: Literal["plot", "character", "world"]
    relation_type: str
    relation_label: str
    # 'outgoing'：当前节点 -> 对方；'incoming'：对方 -> 当前节点。
    direction: Literal["outgoing", "incoming"]


class CrossReferenceResponse(BaseModel):
    """一个节点在其他子图中的全部引用。"""

    node_id: str
    section: Literal["plot", "character", "world"] | None = None
    references: list[CrossReferenceItem] = Field(default_factory=list)


class PositionPayload(BaseModel):
    """Vue Flow 使用的二维节点坐标。"""

    x: float
    y: float


class NodePayload(BaseModel):
    """前后端共享的节点 DTO。

    字段名遵循前端约定，例如 `type`、`nodeType` 和 `typeLabel`，
    以避免在 API 边界引入额外映射成本。
    """

    id: str
    type: str
    nodeType: str | None = None
    title: str
    content: str
    position: PositionPayload
    meta: str = ""
    typeLabel: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "draft"
    parentId: str | None = None
    sortOrder: int = 0


class EdgeWaypointPayload(BaseModel):
    """用户拖动生成的边中点垂直坐标。

    与前端 ``CreativeEdgeWaypoint`` 保持一致；字段保留 camelCase，
    避免 DTO 转换噪声。
    """

    orientation: str  # "horizontal" | "vertical"
    middle: float
    nearSource: float | None = None
    nearTarget: float | None = None


class EdgePayload(BaseModel):
    """Vue Flow 边 DTO。

    存储 handle 和边样式信息，后端读出后前端可以精确恢复连接。
    """

    id: str
    source: str
    target: str
    label: str = ""
    relationType: str = "relates_to"
    sourceHandle: str | None = None
    targetHandle: str | None = None
    type: str = "smoothstep"
    animated: bool = False
    waypoint: EdgeWaypointPayload | None = None


class IndexingStatusPayload(BaseModel):
    """向量索引状态 DTO。

    保存端点会先保证写入 SQLite，再把 embedding/ChromaDB 同步结果带回前端，
    让用户知道语义检索是否真正可用。
    """

    status: str = "not_checked"
    message: str = ""
    provider: str = ""
    model: str = ""
    dimension: int = 0
    expected_nodes: int = 0
    indexed_nodes: int = 0
    missing_node_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class GraphPayload(BaseModel):
    """读取图时返回项目元数据以及完整节点、边快照。"""

    project: ProjectPayload
    nodes: list[NodePayload]
    edges: list[EdgePayload]
    indexing: IndexingStatusPayload = Field(default_factory=IndexingStatusPayload)


class SaveGraphRequest(BaseModel):
    """保存端点请求体。

    保存策略是整体替换图快照；空列表表示清空当前项目图。
    """

    nodes: list[NodePayload] = Field(default_factory=list)
    edges: list[EdgePayload] = Field(default_factory=list)


class UpdateNodeRequest(BaseModel):
    """节点局部更新请求体。

    所有字段都是可选的；`None` 表示不修改该字段。
    """

    title: str | None = None
    content: str | None = None
    position: PositionPayload | None = None
    nodeType: str | None = None
    meta: str | None = None
    typeLabel: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class RagContextRequest(BaseModel):
    """RAG 上下文预览请求。

    当前端点只构建上下文和 prompt，不调用任何 LLM。
    """

    node_id: str
    query: str = ""
    agent_type: str = "inspiration"
    top_k: int = 5


class RagCurrentNodePayload(BaseModel):
    """RAG 响应中的当前节点快照。"""

    id: str
    type: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)


class RagGraphContextItem(BaseModel):
    """由画布边推导出的一跳图关系上下文。"""

    id: str
    type: str
    title: str
    content: str
    relation_label: str
    relation_type: str
    direction: str


class RagVectorContextItem(BaseModel):
    """向量检索命中的相似节点。"""

    id: str
    type: str
    title: str
    content: str
    score: float


class RagMergedContextItem(BaseModel):
    """合并后的上下文条目。"""

    id: str
    source: str
    type: str
    title: str
    content: str


class RagDebugPayload(BaseModel):
    """RAG 上下文构建的调试信息。"""

    query_used: str
    top_k: int
    vector_store: str
    llm_called: bool = False
    vector_error: str | None = None


class MemorySearchRequest(BaseModel):
    """项目级 Lore Memory 搜索请求。"""

    query: str = ""
    node_type: str | None = None
    top_k: int = 6


class MemorySearchItem(BaseModel):
    """项目级 Lore Memory 搜索的命中条目。"""

    id: str
    type: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    status: str = "draft"
    score: float


class MemorySearchResponse(BaseModel):
    """项目级 Lore Memory 搜索响应。"""

    items: list[MemorySearchItem]
    debug: RagDebugPayload


class RagContextResponse(BaseModel):
    """RAG 上下文端点的完整响应。"""

    current_node: RagCurrentNodePayload
    graph_context: list[RagGraphContextItem]
    vector_context: list[RagVectorContextItem]
    merged_context: list[RagMergedContextItem]
    prompt: str
    debug: RagDebugPayload


class ChatSessionCreateRequest(BaseModel):
    """创建聊天会话的请求体。"""

    project_id: str
    title: str = ""


class ChatSessionPayload(BaseModel):
    """聊天会话 DTO。"""

    id: str
    project_id: str
    thread_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionRenameRequest(BaseModel):
    """重命名聊天会话的请求体。"""
    title: str


class SessionTitleRequest(BaseModel):
    """由 LLM 总结会话标题的请求体。"""
    user_message: str

    
class ChatMessageCreateRequest(BaseModel):
    """追加聊天消息的请求体；从第 4 阶段开始，图入口取代直接 POST。"""

    role: Literal["user", "assistant", "system"]
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)


class ChatMessagePayload(BaseModel):
    """聊天消息 DTO。"""

    id: str
    session_id: str
    role: str
    content: str
    meta: dict[str, Any]
    created_at: datetime


class AgentStagingCreateItem(BaseModel):
    """单个暂存项的写入载荷；persistence_hub 和手动端点都会使用。"""

    change_type: Literal[
        "create_node",
        "create_edge",
        "update_node",
        "delete_node",
        "delete_edge",
    ]
    target_id: str | None = None
    pending_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class AgentStagingBatchCreateRequest(BaseModel):
    """同一轮 Agent 中批量写入暂存项的请求体。"""

    message_id: str
    agent_type: str = ""
    items: list[AgentStagingCreateItem] = Field(default_factory=list)


class AgentStagingPayload(BaseModel):
    """单个暂存项 DTO。"""

    id: str
    session_id: str
    message_id: str
    project_id: str
    batch_id: str
    change_type: str
    target_id: str | None
    pending_id: str | None
    payload: dict[str, Any]
    payload_edited: dict[str, Any] | None
    agent_type: str
    reasoning: str
    order_in_batch: int
    status: str
    created_at: datetime
    resolved_at: datetime | None


class AgentStagingBatchPayload(BaseModel):
    """暂存批次 DTO；聚合共享同一 batch_id 的多项变更用于展示。"""

    batch_id: str
    items: list[AgentStagingPayload]


class AgentStagingActionRequest(BaseModel):
    """处理单个暂存项的请求。

    当 ``action='edit'`` 时必须提供 ``payload_edited``；其他动作会忽略它。
    """

    action: Literal["accept", "edit", "reject"]
    payload_edited: dict[str, Any] | None = None


class AgentStagingBatchActionRequest(BaseModel):
    """批量处理暂存项的请求。"""

    action: Literal["accept_all", "reject_all"]


class ChatRequest(BaseModel):
    """触发 agent_graph 推理的请求体。"""

    session_id: str
    user_message: str
    selected_node_ids: list[str] = Field(default_factory=list)
    # 后台 B-agent 开关；默认关闭，避免 question_planner / structured_extractor
    # 在回复完成后继续阻塞本轮聊天。需要自动抽取设定时由前端显式传 True。
    extraction_enabled: bool = False
    # 为 True 时，staging 会立即 accept_all（聊天 UI 中的行内确认卡 + 丢弃）。
    auto_apply_staging: bool = False
    # auto：由启发式判断；on：强制 Tavily；off：本轮绝不调用 web_search。
    web_search_mode: Literal["auto", "on", "off"] = "auto"
    # 用户选择的 agent 模式；"auto" 表示让 intent_router 自由分类。
    preferred_intent: Literal["auto", "research", "inspiration", "structure"] = "auto"


class ChatResponse(BaseModel):
    """一轮 agent 推理后的聊天回复，以及副作用摘要。

    只有本轮产生 staging 时 ``batch_id`` 才有值；前端用它拉取暂存面板内容。
    """

    message_id: str
    reply_text: str
    cited_node_ids: list[str] = Field(default_factory=list)
    intent: str
    batch_id: str | None
    staging_count: int
    staging_summary: str = ""
