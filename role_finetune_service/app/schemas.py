from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class RoleModelRelation(BaseModel):
    """角色图谱里与当前角色直接相连的一条关系。"""

    other_node_id: str
    other_title: str
    other_type: str = ""
    relation_label: str = ""
    relation_type: str = ""
    direction: Literal["outgoing", "incoming"]
    content: str = ""


class RoleModelCrossReference(BaseModel):
    """跨剧情/角色/世界观分区的引用关系。"""

    other_node_id: str
    other_title: str
    other_section: str
    relation_label: str = ""
    relation_type: str = ""
    direction: Literal["outgoing", "incoming"]
    content: str = ""


class RoleModelRelatedNode(BaseModel):
    """压缩后的相关节点，用作训练数据的背景材料。"""

    id: str
    title: str
    node_type: str
    content: str = ""
    relation_label: str = ""


class RoleModelSnapshot(BaseModel):
    """主后端导出的角色快照。

    训练服务只消费这份快照，不直接访问桌面端数据库。这样 GPU 训练服务可以独立
    部署，也能在任务目录中保存当时训练所用资料，便于复现。
    """

    project_id: str
    project_name: str = ""
    character_id: str
    character_name: str
    character_summary: str = ""
    fields: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    relations: list[RoleModelRelation] = Field(default_factory=list)
    cross_references: list[RoleModelCrossReference] = Field(default_factory=list)
    related_nodes: list[RoleModelRelatedNode] = Field(default_factory=list)
    project_seed: str = ""


class RoleMaterialBrief(BaseModel):
    """资料 agent 整理后的角色训练档案。

    原始快照保留事实证据，这个 brief 负责把事实加工成训练更容易使用的维度：
    身份、性格、说话方式、关系线、世界观约束和边界策略。
    """

    identity: str = ""
    personality: str = ""
    voice_style: str = ""
    known_facts: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    world_context: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    sample_plan: list[str] = Field(default_factory=list)


class CreateJobRequest(BaseModel):
    """创建训练任务的请求体。"""

    snapshot: RoleModelSnapshot
    material_brief: RoleMaterialBrief | None = None
    sample_count: int | None = None


class RoleModelJob(BaseModel):
    """训练任务状态。

    路径字段都指向训练服务工作区内的产物，供前端展示和排查，不会被桌面 app 打包。
    """

    id: str
    project_id: str
    character_id: str
    character_name: str
    status: JobStatus
    sample_count: int = 0
    dataset_path: str = ""
    dataset_info_path: str = ""
    train_config_path: str = ""
    adapter_path: str = ""
    material_brief_path: str = ""
    log_tail: str = ""
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class RoleChatMessage(BaseModel):
    """聊天历史中的一轮消息，兼容 OpenAI-style role/content 结构。"""

    role: Literal["user", "assistant", "system"]
    content: str


class RoleChatLogItem(BaseModel):
    """训练服务持久化的一条角色聊天消息。"""

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class RoleChatRequest(BaseModel):
    """角色对话请求。

    `fallback_snapshot` 由主后端传入。即便 adapter 已经训练好，推理时仍可使用最新
    快照补充上下文；如果模型 API 不可用，也能用这份资料完成演示兜底。
    """

    message: str
    history: list[RoleChatMessage] = Field(default_factory=list)
    fallback_snapshot: RoleModelSnapshot | None = None


class HealthResponse(BaseModel):
    """健康检查返回值，用于主 app 判断训练服务是否在线。"""

    status: str = "ok"
    service: str = "role-finetune-service"
    workspace: str
    dry_run: bool
    model_api_configured: bool
    model_api_auto_start: bool = False
    active_model_job_id: str | None = None
    active_model_api_url: str | None = None
    active_model_api_pid: int | None = None
    active_model_api_config: str | None = None
    active_model_api_log: str | None = None
    dataset_api_configured: bool


JsonDict = dict[str, Any]
