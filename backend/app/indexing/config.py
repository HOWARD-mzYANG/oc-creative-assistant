"""向量索引配置常量。

本模块集中管理 ChromaDB collection 名称、embedding 维度，以及检索相关默认值。
路径配置来自 `app.core.paths`：开发模式默认 `backend/data`，打包模式跟随 Electron 指定目录。
embedding 与索引调试相关的运行时配置统一从 `app.core.settings` 读取，避免 .env 解析散落到多个模块。
"""

from app.core.paths import CHROMA_PATH
from app.core.settings import get_embedding_settings, get_indexing_settings


COLLECTION_BY_NODE_TYPE: dict[str, str] = {
    "character": "oc_characters",
    "worldbuilding": "oc_worldbuilding",
    "plot": "oc_plot",
}
DEFAULT_COLLECTION_NAME = "oc_misc"
DEFAULT_RELATION_LABEL = "related"
DEFAULT_RELATION_TYPE = "relates_to"
DEFAULT_NODE_STATUS = "draft"

# Embedding / 索引配置在模块导入时快照一次，避免热路径反复读取 .env。
_embedding_settings = get_embedding_settings()
_indexing_settings = get_indexing_settings()

# 这些常量同时被 vector_store 和 sync 使用；保留模块级别别名以兼容既有 import 路径。
EMBEDDING_BASE_URL = _embedding_settings.base_url or ""
EMBEDDING_API_KEY = _embedding_settings.api_key or ""
EMBEDDING_MODEL = _embedding_settings.model
EMBEDDING_DIMENSION = _embedding_settings.dimension

# 索引同步日志默认关闭，避免增量同步细节刷屏 Electron/uvicorn 控制台；排查问题时可在 .env 中开启。
INDEXING_DEBUG_LOG = _indexing_settings.debug_log

MAX_TOP_K = 20
