"""LangGraph 持久化 Checkpointer 单例。

将 AgentState 的中间快照写入独立 sqlite 文件（与业务数据库分离以避免事务冲突）；连接不会在
import 时打开，而是在 ``build_graph`` 编译图时按需触发。

``check_same_thread=False`` 是 FastAPI 多线程模型下的必要参数：SQLite 默认禁止跨线程共享
连接，关闭该检查后由 SqliteSaver 自身的锁保证安全。
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.settings import get_agent_settings


_ALLOWED_MSGPACK_MODULES: list[tuple[str, str]] = [
    ("app.agents.schemas", "IntentClassification"),
    ("app.agents.schemas", "InspirationOutput"),
    ("app.agents.schemas", "ResearchOutput"),
    ("app.agents.schemas", "StructureOutput"),
    ("app.agents.schemas", "SimulationOutput"),
    ("app.agents.schemas", "SimulationBranch"),
    ("app.agents.schemas", "ChatAssemblerOutput"),
    ("app.agents.schemas", "ProposedChange"),
    ("app.schemas", "RagCurrentNodePayload"),
    ("app.schemas", "RagGraphContextItem"),
    ("app.schemas", "RagVectorContextItem"),
    ("app.schemas", "RagMergedContextItem"),
]


@lru_cache(maxsize=1)
def get_checkpointer() -> SqliteSaver:
    """返回 LangGraph Checkpointer 单例。"""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    settings = get_agent_settings()
    settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        settings.checkpointer_db_path.as_posix(),
        check_same_thread=False,
    )
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES)
    return SqliteSaver(conn, serde=serde)
