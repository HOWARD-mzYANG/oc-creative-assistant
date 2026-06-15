"""SQLAlchemy 数据库连接与初始化。

本模块只处理 SQLite engine、Session 工厂、ORM 元数据初始化，以及旧数据库的轻量兼容。
业务校验位于服务层，向量索引位于 `app.indexing`。
"""

import json
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.paths import DATABASE_PATH


DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    """所有 ORM 模型共享的声明式基类。"""


# 本地 SQLite 文件位于 backend/data；路径集中在 app.core.paths，避免受包层级影响。
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _deserialize_json(value: str | None) -> Any:
    """反序列化 SQLite JSON 字段，同时兼容旧数据库中的纯字符串 meta。

    参数：
        value: SQLAlchemy JSON 反序列化前的原始文本。

    返回：
        解析后的 Python 对象；旧版非 JSON 字符串会原样返回。
    """
    if value is None:
        return {}

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    json_deserializer=_deserialize_json,
    future=True,
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """为每个 SQLite 连接启用外键约束。

    SQLite 默认不强制执行外键；这里确保 `ondelete=\"CASCADE\"` 在本地桌面数据库中真正生效。
    """
    if isinstance(dbapi_connection, SQLiteConnection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """初始化 ORM 表结构，并为旧 PoC 数据库回填轻量兼容字段。"""
    # 延迟导入模型，确保 create_all 前 Base.metadata 已注册所有表。
    from app.db.models import (  # noqa: F401
        AgentStagingORM,
        ChatMessageORM,
        ChatSessionORM,
        EdgeORM,
        GraphORM,
        NodeORM,
        ProjectORM,
        ProjectSeedORM,
    )

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema_compatibility()
    _ensure_subgraph_backfill()


def _ensure_sqlite_schema_compatibility() -> None:
    """为旧 PoC 数据库回填新增列。

    项目尚未引入完整迁移系统；这里只处理已发出本地数据库所需的最低兼容。
    """
    with engine.begin() as connection:
        edge_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(edges)").fetchall()
        }

        if "relation_type" not in edge_columns:
            connection.exec_driver_sql(
                "ALTER TABLE edges ADD COLUMN relation_type VARCHAR NOT NULL DEFAULT 'relates_to'"
            )

        if "waypoint" not in edge_columns:
            connection.exec_driver_sql("ALTER TABLE edges ADD COLUMN waypoint TEXT")

        project_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(projects)").fetchall()
        }
        if "world_brief" not in project_columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN world_brief TEXT NOT NULL DEFAULT ''"
            )

        session_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(chat_sessions)"
            ).fetchall()
        }
        if "summary_message_count" not in session_columns:
            connection.exec_driver_sql(
                "ALTER TABLE chat_sessions ADD COLUMN summary_message_count INTEGER NOT NULL DEFAULT 0"
            )

        # first_revision 第 1 阶段：多子图架构需要的新列。
        # create_all 只创建新表（graphs / project_seeds），不会给旧表加列，因此这里手动补齐。
        if "description" not in project_columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )
        if "cover_image" not in project_columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN cover_image TEXT NOT NULL DEFAULT ''"
            )
        for column in ("plot_graph_id", "character_graph_id", "world_graph_id"):
            if column not in project_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE projects ADD COLUMN {column} VARCHAR"
                )

        node_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(nodes)").fetchall()
        }
        if "graph_id" not in node_columns:
            connection.exec_driver_sql("ALTER TABLE nodes ADD COLUMN graph_id VARCHAR")


# node_type -> 子图 section 的分配规则。
# 决策：plot/character/world 各归属自己的 section；idea/research/structure 等其他类型暂归 plot。
_SECTION_BY_NODE_TYPE: dict[str, str] = {
    "character": "character",
    "worldbuilding": "world",
    "plot": "plot",
}
_DEFAULT_SECTION = "plot"


def _ensure_subgraph_backfill() -> None:
    """为项目补齐三个子图，并相应放置缺少归属的节点。

    幂等：旧项目会创建 plot / character / world 三个子图；已经有子图的项目会继续检查
    节点 ``graph_id`` 是否缺失。这样可以修复默认图被项目级 ``replace_graph`` 重写后，
    节点存在但三个子图页面为空的问题。
    """
    import uuid

    from app.db.models import GraphORM, NodeORM, ProjectORM

    with SessionLocal.begin() as session:
        projects = session.query(ProjectORM).all()
        for project in projects:
            graph_ids: dict[str, str] = {}
            section_attrs = {
                "plot": "plot_graph_id",
                "character": "character_graph_id",
                "world": "world_graph_id",
            }
            for section in ("plot", "character", "world"):
                attr = section_attrs[section]
                graph_id = getattr(project, attr)
                graph = session.get(GraphORM, graph_id) if graph_id else None
                if graph is None or graph.project_id != project.id or graph.section != section:
                    graph = (
                        session.query(GraphORM)
                        .filter(
                            GraphORM.project_id == project.id,
                            GraphORM.section == section,
                        )
                        .first()
                    )
                if graph is None:
                    graph = GraphORM(
                        id=uuid.uuid4().hex,
                        project_id=project.id,
                        section=section,
                    )
                    session.add(graph)
                graph_ids[section] = graph.id
                setattr(project, attr, graph.id)

            valid_graph_ids = set(graph_ids.values())
            nodes = session.query(NodeORM).filter(NodeORM.project_id == project.id).all()
            for node in nodes:
                if node.graph_id in valid_graph_ids:
                    continue
                section = _SECTION_BY_NODE_TYPE.get(node.node_type, _DEFAULT_SECTION)
                node.graph_id = graph_ids[section]
