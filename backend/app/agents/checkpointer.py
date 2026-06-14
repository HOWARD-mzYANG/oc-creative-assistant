"""LangGraph persistence Checkpointer singleton.

Writes AgentState intermediate snapshots to a dedicated sqlite file (separate
from the business database to avoid transaction conflicts); the connection is
not opened at import time, but triggered on demand by ``build_graph`` at
compile time.

``check_same_thread=False`` is a required parameter under FastAPI's
multi-threaded model: SQLite by default forbids sharing a connection across
threads, and once disabled, safety is guaranteed by SqliteSaver's own locking.
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
    """返回 LangGraph Checkpointer singleton."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    settings = get_agent_settings()
    settings.checkpointer_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        settings.checkpointer_db_path.as_posix(),
        check_same_thread=False,
    )
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES)
    return SqliteSaver(conn, serde=serde)