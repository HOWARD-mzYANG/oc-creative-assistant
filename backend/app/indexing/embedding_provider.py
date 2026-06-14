"""Embedding provider。

把“如何将文本转换为向量”封装到单独模块，让 vector_store 只关心 ChromaDB collections 和
文档读写。生产环境优先使用真实 DashScope 模型；配置缺失或 SDK 初始化失败时，回退到本地
hash 占位 provider，确保 RAG 流水线在离线 / CI 场景下仍可工作。

进程级单例 ``embedding_provider`` 在模块导入时确定，并由索引同步和查询共同使用，避免不同
路径使用不同模型导致向量空间不一致。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from functools import lru_cache
from typing import Any

from app.core.settings import get_embedding_settings, get_indexing_settings
from app.indexing.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    INDEXING_DEBUG_LOG,
)


logger = logging.getLogger(__name__)


def _log(message: str) -> None:
    """打印 embedding API 调用信息，使真实执行路径可观察；来源与 vector_store._log 一致。"""
    if INDEXING_DEBUG_LOG:
        print(f"[embedding] {message}", flush=True)


class HashEmbeddingProvider:
    """PoC 占位 embedding provider。

    当真实 embedding 服务（DashScope）未配置、依赖缺失或 SDK 初始化失败时用作本地回退，确保
    ChromaDB 写入和查询不被网络 / 配置问题打断。其属性命名与 ``DashScopeEmbeddingProvider``
    保持一致，使 ``app.indexing.sync`` 可直接读取 ``name``/``model``/``dimension``，无需区分
    provider 类型。
    """

    name = "hash"
    base_url = ""
    model = "hash"

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        """允许测试或回退路径显式覆盖向量维度；默认使用全局 EMBEDDING_DIMENSION。"""
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        """将单段文本转换为固定维度向量。"""
        return self._embed_single(text)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """批量将文本转换为固定维度向量；与真实 provider 接口保持一致。"""
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        """将单段文本做 token hash，得到归一化向量。

        参数：
            text: 要向量化的文本。
        返回：
            归一化后的固定维度向量；空文本返回全零向量。
        """
        tokens = self._tokenize(text)
        vector = [0.0] * self.dimension

        for token in tokens:
            # hash 到固定维度可让同一 token 稳定落到同一槽位，便于 PoC 阶段可复现检索。
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))

        if norm == 0:
            return vector

        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        """为 hash embedding 生成 token。

        参数：
            text: 原始文本。
        返回：
            英文/数字词、单个中文字符和字符 bigram 的组合 token 列表。
        """
        lowered = text.lower()
        words = re.findall(r"[\w]+", lowered, flags=re.UNICODE)
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        char_bigrams = [text[index : index + 2] for index in range(max(len(text) - 1, 0))]
        return words + chinese_chars + char_bigrams


class DashScopeEmbeddingProvider:
    """阿里 DashScope embedding provider。

    DashScope 提供 OpenAI 兼容接口，因此这里复用 openai SDK，避免新增依赖。该 provider 在写入
    ChromaDB 和查询 ChromaDB 时使用同一个向量模型，确保向量空间一致。
    """

    name = "dashscope"

    def __init__(self, api_key: str, base_url: str, model: str, dimension: int) -> None:
        """保存 embedding API 配置；实际 client 创建延迟到首次调用，避免无关导入影响启动。"""
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.dimension = dimension
        self._client: Any | None = None

    def embed(self, text: str) -> list[float]:
        """将单段文本转换为语义向量。"""
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """批量调用阿里 embedding API。"""
        if not texts:
            return []

        _log(f"call embedding api model={self.model} dimension={self.dimension} batch_size={len(texts)}")
        response = self._get_client().embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimension,
            encoding_format="float",
        )
        vectors_by_index: dict[int, list[float]] = {}

        for offset, item in enumerate(response.data):
            index = getattr(item, "index", offset)
            vector = list(item.embedding)

            if len(vector) != self.dimension:
                raise RuntimeError(
                    f"Embedding 维度不匹配：期望 {self.dimension}，实际 {len(vector)}"
                )

            vectors_by_index[int(index)] = vector

        vectors = [vectors_by_index[index] for index in range(len(texts))]
        _log(f"embedding api success model={self.model} vectors={len(vectors)} dimension={self.dimension}")
        return vectors

    def _get_client(self) -> Any:
        """延迟初始化 OpenAI 兼容 client，避免启动时暴露 API key 配置问题。"""
        if not self.api_key:
            raise RuntimeError("未设置 OC_EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY，无法调用阿里 embedding API")

        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError("未安装 openai 依赖，无法调用阿里 embedding API") from error

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        return self._client


def _build_embedding_provider() -> Any:
    """根据 .env 配置选择真实 provider 或本地 hash 占位 provider。

    优先使用已配置的 DashScope；配置缺失或 SDK 初始化失败时回退到 hash provider，确保 RAG
    流水线始终可用，方便离线开发和 CI。
    """
    settings = get_embedding_settings()
    indexing = get_indexing_settings()

    if not settings.is_configured:
        if indexing.debug_log:
            logger.warning("未配置 OC_EMBEDDING_*，使用本地 hash embedding 占位实现")
        return HashEmbeddingProvider(EMBEDDING_DIMENSION)

    try:
        provider = DashScopeEmbeddingProvider(
            settings.api_key or EMBEDDING_API_KEY,
            settings.base_url or EMBEDDING_BASE_URL,
            settings.model or EMBEDDING_MODEL,
            settings.dimension,
        )
        if indexing.debug_log:
            logger.info(
                "DashScope embedding enabled: model=%s dim=%d",
                settings.model,
                settings.dimension,
            )
        return provider
    except Exception as error:  # noqa: BLE001
        logger.warning("DashScope embedding 初始化失败，回退到 hash 占位实现：%s", error)
        return HashEmbeddingProvider(EMBEDDING_DIMENSION)


embedding_provider = _build_embedding_provider()


@lru_cache(maxsize=2048)
def _cached_query_embedding(text: str) -> tuple[float, ...]:
    """进程级查询 embedding 缓存；使用 tuple 便于 lru_cache 哈希，调用方再转回 list。

    仅用于“查询路径”；写入路径（upsert 文档 embedding）不能缓存，因为每个文档内容不同，不会命中。
    """
    return tuple(embedding_provider.embed(text))


def embed_query(text: str) -> list[float]:
    """带 LRU 缓存的查询 embedding 入口；tool_loop / RAG / parallel_retrieval 都走这里。"""
    return list(_cached_query_embedding(text))


def get_embedding_signature() -> str:
    """返回当前 embedding 配置签名。

    ChromaDB 会存储该签名，用于判断模型、base_url 或维度变化后是否需要重写向量。
    """
    return (
        f"{embedding_provider.name}:"
        f"{getattr(embedding_provider, 'base_url', '')}:"
        f"{embedding_provider.model}:"
        f"{embedding_provider.dimension}"
    )
