"""应用运行时配置。

集中读取 .env / 环境变量，避免业务模块直接依赖 os.getenv，便于后续切换到
pydantic-settings 或注入测试配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.core.paths import BACKEND_ROOT, DATA_DIR


def _load_env() -> None:
    """将 backend/.env 加载到当前进程环境变量中。

    模块导入时只运行一次；.env 不存在时静默跳过，使没有 .env 的环境（如 CI）仍可启动
    （此时会回退到占位 embedding）。
    """
    env_path: Path = BACKEND_ROOT / ".env"
    load_dotenv(env_path, override=False)


_load_env()


def _get_bool(name: str, default: bool = False) -> bool:
    """读取布尔环境变量，将 1/true/yes/on 视为 True。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    values = [
        item.strip().lower()
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    ]
    return tuple(values) or default


@dataclass(frozen=True)
class EmbeddingSettings:
    """Embedding 服务配置。"""

    base_url: str | None
    api_key: str | None
    model: str
    dimension: int

    @property
    def is_configured(self) -> bool:
        """判断调用真实 embedding 服务所需的最低配置是否存在。"""
        return bool(self.base_url and self.api_key and self.model)


@dataclass(frozen=True)
class IndexingSettings:
    """索引调试相关开关。"""

    debug_log: bool


def get_embedding_settings() -> EmbeddingSettings:
    return EmbeddingSettings(
        base_url=os.getenv("OC_EMBEDDING_BASE_URL"),
        api_key=os.getenv("OC_EMBEDDING_API_KEY"),
        model=os.getenv("OC_EMBEDDING_MODEL", "text-embedding-v4"),
        dimension=_get_int("OC_EMBEDDING_DIMENSION", 1024),
    )


def get_indexing_settings() -> IndexingSettings:
    return IndexingSettings(debug_log=_get_bool("OC_INDEXING_DEBUG_LOG", False))


@dataclass(frozen=True)
class LlmSettings:
    """聊天 LLM 服务配置。

    ``provider`` 决定策略模式的实现选择：``openai`` 使用真实 OpenAI 兼容协议
    （DeepSeek / 通义 / 官方 OpenAI），``mock`` 使用本地确定性桩，供离线开发和单测使用。
    """

    provider: str
    base_url: str | None
    api_key: str | None
    model: str
    structured_methods: tuple[str, ...]
    stream_reasoning: bool

    @property
    def is_configured(self) -> bool:
        if self.provider == "mock":
            return True
        return bool(self.base_url and self.api_key and self.model)


def get_llm_settings() -> LlmSettings:
    structured_methods = _get_csv(
        "OC_LLM_STRUCTURED_METHODS",
        _get_csv(
            "OC_LLM_STRUCTURED_METHOD",
            ("function_calling", "json_mode", "plain_json"),
        ),
    )
    return LlmSettings(
        provider=os.getenv("OC_LLM_PROVIDER", "openai").strip().lower(),
        base_url=os.getenv("OC_LLM_BASE_URL"),
        api_key=os.getenv("OC_LLM_API_KEY"),
        model=os.getenv("OC_LLM_MODEL", "deepseek/deepseek-chat"),
        structured_methods=structured_methods,
        stream_reasoning=_get_bool("OC_LLM_STREAM_REASONING", False),
    )


@dataclass(frozen=True)
class WebSearchSettings:
    """联网搜索工具配置。

    api_key 为空时，``web_search`` 工具会直接返回降级提示而不是报错，确保未配置 key 的
    离线开发和 CI/单测仍能跑完整 Agent 流水线。
    """

    provider: str
    api_key: str | None
    timeout_seconds: int

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


def get_web_search_settings() -> WebSearchSettings:
    return WebSearchSettings(
        provider=os.getenv("OC_WEB_SEARCH_PROVIDER", "tavily").strip().lower(),
        api_key=os.getenv("OC_WEB_SEARCH_API_KEY") or None,
        timeout_seconds=_get_int("OC_WEB_SEARCH_TIMEOUT", 10),
    )


@dataclass(frozen=True)
class AgentSettings:
    """Agent 图运行时配置。

    ``checkpointer_db_path`` 提供 LangGraph SqliteSaver 的持久化路径，并与业务 SQLite
    分离以避免事务冲突；``context_token_cap`` 控制每轮注入对话的检索上下文上限，避免
    长项目把 prompt 撑爆 LLM 窗口。

    多层记忆相关：
    - ``recent_message_window``：load_context 原样取最近 N 条消息喂给 prompt
    - ``summary_keep_recent``：摘要压缩时保留多少条最新消息不纳入摘要
    - ``summary_compress_every``：超过高水位后再积累多少条旧消息才再次触发压缩
    """

    checkpointer_db_path: Path
    context_token_cap: int
    recent_message_window: int
    summary_keep_recent: int
    summary_compress_every: int


def get_agent_settings() -> AgentSettings:
    return AgentSettings(
        checkpointer_db_path=DATA_DIR / "langgraph_checkpoint.sqlite3",
        context_token_cap=_get_int("OC_AGENT_CONTEXT_TOKEN_CAP", 2000),
        recent_message_window=_get_int("OC_AGENT_RECENT_MESSAGE_WINDOW", 10),
        summary_keep_recent=_get_int("OC_AGENT_SUMMARY_KEEP_RECENT", 10),
        summary_compress_every=_get_int("OC_AGENT_SUMMARY_COMPRESS_EVERY", 6),
    )


@dataclass(frozen=True)
class AppSettings:
    """应用级运行时开关。"""

    dev_mode: bool


def get_app_settings() -> AppSettings:
    return AppSettings(dev_mode=_get_bool("OC_DEV_MODE", False))
