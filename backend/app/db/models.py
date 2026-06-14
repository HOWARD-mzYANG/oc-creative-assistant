"""图谱领域的 SQLAlchemy ORM 模型。

项目是图谱的生命周期边界；节点和边都归属于项目。本模块只描述数据库结构与 ORM 关系，
不处理 API DTO 转换或业务校验。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ProjectORM(Base):
    """Projects 表。

    当前 PoC 只创建默认项目，但结构保留多项目能力。
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    world_brief: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # first_revision 决策 1：项目简介，用于项目库卡片 / 工作区概览编辑 / seed 组装。
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # 可选封面图，以 base64 data URL 存储；显示在概览页并作为项目库卡片背景。
    cover_image: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # 一个 Project 下的三个独立子图。这里刻意省略 DB 级 ForeignKey：projects<->graphs
    # 互相引用会形成建表循环，且 SQLite 不支持 ALTER ADD CONSTRAINT；与 EdgeORM 端点处理
    # 一致，改由服务层校验一致性（见 graph_validation）。
    plot_graph_id: Mapped[str | None] = mapped_column(String, nullable=True)
    character_graph_id: Mapped[str | None] = mapped_column(String, nullable=True)
    world_graph_id: Mapped[str | None] = mapped_column(String, nullable=True)
    nodes: Mapped[list["NodeORM"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["EdgeORM"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    graphs: Mapped[list["GraphORM"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    seeds: Mapped[list["ProjectSeedORM"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class NodeORM(Base):
    """画布节点表。

    节点存储角色、世界观、剧情等创作内容，也是向量索引的主要数据源。
    """

    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_project_sort_order", "project_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # first_revision 决策 1：节点归属于特定子图。迁移旧数据库时允许为空，并通过 node_type
    # 回填；新创建节点必须携带 graph_id。
    graph_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("graphs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    node_type: Mapped[str] = mapped_column("type", String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    type_label: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0"))
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[ProjectORM] = relationship(back_populates="nodes")


class EdgeORM(Base):
    """画布边表。

    边存储 Vue Flow 端点、handle 和创作关系类型。端点同项目一致性由服务层校验，避免在
    PoC 阶段引入复杂复合外键。
    """

    __tablename__ = "edges"
    __table_args__ = (
        Index("ix_edges_project_sort_order", "project_id", "sort_order"),
        Index("ix_edges_source", "source"),
        Index("ix_edges_target", "target"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String,
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(
        String,
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    source_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    target_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    edge_type: Mapped[str] = mapped_column(
        "type",
        String,
        nullable=False,
        default="smoothstep",
        server_default="smoothstep",
    )
    relation_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="relates_to",
        server_default="relates_to",
    )
    waypoint: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    animated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[ProjectORM] = relationship(back_populates="edges")
    source_node: Mapped[NodeORM] = relationship(
        "NodeORM",
        foreign_keys=[source],
        passive_deletes=True,
    )
    target_node: Mapped[NodeORM] = relationship(
        "NodeORM",
        foreign_keys=[target],
        passive_deletes=True,
    )


class ChatSessionORM(Base):
    """聊天会话表。

    一个 session 对应前端一个聊天面板上下文；``thread_id`` 供 LangGraph Checkpointer
    使用，使同一会话在页面刷新后仍能从 sqlite 取回中间状态。``conversation_summary``
    由摘要压缩节点定期更新，用于避免长对话撑爆 token 预算。
    """

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="", server_default="")
    conversation_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # 核心事实层：summary_compress 每轮抽取的关键设定 / 决策，跨轮累积，不被
    # conversation_summary 的重压缩覆盖，解决“长对话后早期事实被遗忘”的核心痛点。
    key_facts: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    # 高水位：摘要已覆盖多少条开头消息；用于摘要压缩的增量节流，避免每轮都重压缩。
    summary_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[ProjectORM] = relationship()
    messages: Mapped[list["ChatMessageORM"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessageORM.created_at",
    )
    staging_items: Mapped[list["AgentStagingORM"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessageORM(Base):
    """聊天消息表。

    消息只追加，不原地修改；``meta`` 用于附加 cited_node_ids / agent_type 等扩展字段，
    避免每新增一个上下文字段就改表结构。
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped[ChatSessionORM] = relationship(back_populates="messages")
    staging_items: Mapped[list["AgentStagingORM"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class AgentStagingORM(Base):
    """Agent 待处理变更表。

    Agent 想执行的画布操作会先暂存在这里，只有用户在前端暂存面板中接受 / 编辑 / 拒绝后，
    才决定是否真正应用到画布。同一回合产生的多项变更共享 ``batch_id``，支持批量
    “全部接受” / “全部拒绝”；``pending_id`` 为同批次新节点分配占位 ID，使边可以引用
    尚未持久化的新节点，并在提交时回填真实 node_id。
    """

    __tablename__ = "agent_staging"
    __table_args__ = (
        Index("ix_agent_staging_session_status", "session_id", "status"),
        Index("ix_agent_staging_batch_order", "batch_id", "order_in_batch"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pending_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    payload_edited: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=""
    )
    reasoning: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    order_in_batch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped[ChatSessionORM] = relationship(back_populates="staging_items")
    message: Mapped[ChatMessageORM] = relationship(back_populates="staging_items")


class GraphORM(Base):
    """子图表（first_revision 决策 1）。

    一个 Project 包含三个独立子图：剧情线（plot）/ 角色卡（character）/ 世界观（world）。
    节点通过 ``NodeORM.graph_id`` 归属到特定子图；``section`` 使用字符串而非数据库 Enum，
    与 ``NodeORM.node_type`` 的处理一致，简化迁移。
    """

    __tablename__ = "graphs"
    __table_args__ = (
        Index("ix_graphs_project_section", "project_id", "section"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # section 属于 {'plot', 'character', 'world'}
    section: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[ProjectORM] = relationship(back_populates="graphs")


class ProjectSeedORM(Base):
    """项目 seeds 表（first_revision 决策 3）。

    seed 是项目当前状态（世界观 / 角色 / 剧情 / 风格）的压缩快照，会在 Chat Agent 启动时
    注入。每次重建都会递增版本，``source`` 记录触发来源。由 seed_compressor（第 5 阶段）
    写入；这里先创建表，为第 1 阶段数据模型升级铺路。
    """

    __tablename__ = "project_seeds"
    __table_args__ = (
        Index("ix_project_seeds_project_version", "project_id", "version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    seed_json: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # source 属于 {'chat_end', 'user_edit'}
    source: Mapped[str] = mapped_column(String, nullable=False, default="user_edit", server_default="user_edit")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[ProjectORM] = relationship(back_populates="seeds")
