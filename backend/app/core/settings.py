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
    """读取整数环境变量，缺失或非法时回退到默认值。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """读取逗号/分号分隔的环境变量，并统一转成小写元组。"""
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
    """读取 Embedding 服务配置，并返回不可变设置对象。"""
    return EmbeddingSettings(
        base_url=os.getenv("OC_EMBEDDING_BASE_URL"),
        api_key=os.getenv("OC_EMBEDDING_API_KEY"),
        model=os.getenv("OC_EMBEDDING_MODEL", "text-embedding-v4"),
        dimension=_get_int("OC_EMBEDDING_DIMENSION", 1024),
    )


def get_indexing_settings() -> IndexingSettings:
    """读取索引同步调试开关配置。"""
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
        """判断当前 LLM provider 是否具备可调用的最低配置。"""
        if self.provider == "mock":
            return True
        return bool(self.base_url and self.api_key and self.model)


def get_llm_settings() -> LlmSettings:
    """读取主 agent LLM 配置及结构化输出策略。"""
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


def has_reply_llm_settings() -> bool:
    """判断是否单独配置了回复润色模型。

    只有 provider / base_url / api_key / model 这类真实路由字段非空时才启用独立
    provider；``OC_LLM_REPLY_STREAM_REASONING=false`` 这类默认开关不会单独触发，
    避免只写占位配置就意外多初始化一个相同模型。
    """
    return any(
        (os.getenv(name) or "").strip()
        for name in (
            "OC_LLM_REPLY_PROVIDER",
            "OC_LLM_REPLY_BASE_URL",
            "OC_LLM_REPLY_API_KEY",
            "OC_LLM_REPLY_MODEL",
        )
    )


def get_reply_llm_settings() -> LlmSettings:
    """读取 chat_assembler 专用的可选快模型配置。

    该模型只负责把上游 agent 的结构化结果改写成最终自然语言回复；未配置时复用主
    LLM。通常这里可以填非 thinking / 更便宜的模型，而主 agent 继续使用更强模型。
    """
    base = get_llm_settings()
    structured_methods = _get_csv(
        "OC_LLM_REPLY_STRUCTURED_METHODS",
        base.structured_methods,
    )
    return LlmSettings(
        provider=os.getenv("OC_LLM_REPLY_PROVIDER", base.provider).strip().lower(),
        base_url=os.getenv("OC_LLM_REPLY_BASE_URL") or base.base_url,
        api_key=os.getenv("OC_LLM_REPLY_API_KEY") or base.api_key,
        model=os.getenv("OC_LLM_REPLY_MODEL") or base.model,
        structured_methods=structured_methods,
        stream_reasoning=_get_bool("OC_LLM_REPLY_STREAM_REASONING", False),
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
        """判断联网搜索服务是否配置了可用 API key。"""
        return bool(self.api_key)


def get_web_search_settings() -> WebSearchSettings:
    """读取联网搜索 provider、API key 和超时配置。"""
    return WebSearchSettings(
        provider=os.getenv("OC_WEB_SEARCH_PROVIDER", "tavily").strip().lower(),
        api_key=os.getenv("OC_WEB_SEARCH_API_KEY") or None,
        timeout_seconds=_get_int("OC_WEB_SEARCH_TIMEOUT", 10),
    )


@dataclass(frozen=True)
class RoleFinetuneSettings:
    """Optional external role-LoRA training service configuration."""

    base_url: str | None
    timeout_seconds: int

    @property
    def is_configured(self) -> bool:
        """判断外部角色微调服务是否配置了基础 URL。"""
        return bool(self.base_url)


def get_role_finetune_settings() -> RoleFinetuneSettings:
    """读取可选的角色微调服务配置。"""
    base_url = os.getenv("OC_ROLE_FINETUNE_BASE_URL")
    return RoleFinetuneSettings(
        base_url=base_url.rstrip("/") if base_url else None,
        timeout_seconds=_get_int("OC_ROLE_FINETUNE_TIMEOUT", 10),
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
    """读取 LangGraph checkpoint、上下文预算和摘要压缩水位配置。"""
    return AgentSettings(
        checkpointer_db_path=DATA_DIR / "langgraph_checkpoint.sqlite3",
        context_token_cap=_get_int("OC_AGENT_CONTEXT_TOKEN_CAP", 6000),
        recent_message_window=_get_int("OC_AGENT_RECENT_MESSAGE_WINDOW", 10),
        summary_keep_recent=_get_int("OC_AGENT_SUMMARY_KEEP_RECENT", 16),
        summary_compress_every=_get_int("OC_AGENT_SUMMARY_COMPRESS_EVERY", 20),
    )


@dataclass(frozen=True)
class AppSettings:
    """应用级运行时开关。"""

    dev_mode: bool


def get_app_settings() -> AppSettings:
    """读取应用级运行时开关配置。"""
    return AppSettings(dev_mode=_get_bool("OC_DEV_MODE", False))
