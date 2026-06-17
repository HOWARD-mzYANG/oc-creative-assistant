"""Prompt 加载器。

按 `name + version` 从 prompts 目录读取 .md 文件，并用 LRU 缓存结果。
这样 prompt 文本与 Python 逻辑解耦，后续改文案或灰度版本时不需要改业务代码。

文件命名约定：``{name}.{version}.md``，例如 ``structure.v1.md``。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).parent

DEFAULT_VERSIONS: dict[str, str] = {
    "structure": "v1",
    "inspiration": "v1",
    "research": "v1",
    "simulation": "v1",
    "intent_router": "v1",
    "chat_assembler": "v1",
    "chat_assembler_small_talk": "v1",
    "chat_assembler_reply": "v1",
    "chat_assembler_metadata": "v1",
    "summary_compress": "v1",
    "role_material_brief": "v1",
}
"""各 prompt 当前启用的版本；需要灰度发布时在这里切换。"""


@lru_cache(maxsize=None)
def load_prompt(name: str, version: str | None = None) -> str:
    """读取并缓存 prompt 文本；文件缺失时直接抛出 FileNotFoundError，便于启动阶段暴露问题。"""
    actual_version = version or DEFAULT_VERSIONS.get(name, "v1")
    path = PROMPTS_DIR / f"{name}.{actual_version}.md"
    return path.read_text(encoding="utf-8").strip()


def get_prompt_version(name: str) -> str:
    """返回当前使用的 prompt 版本，供埋点和调试日志使用。"""
    return DEFAULT_VERSIONS.get(name, "v1")
