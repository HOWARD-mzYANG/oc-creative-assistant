"""工作区底部聊天框的 SSE 流（second_revision 变更 B / W5）。

把被动灵感 agent 的单次输出包装为 SSE 事件，并推送到前端右侧面板。LLM 调用是同步阻塞的，
因此放到线程里运行，避免阻塞事件循环；这与 chat_stream 的处理方式保持一致。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.agents.workspace_inspiration import generate_workspace_output


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_workspace_chat(
    project_id: str,
    message: str,
    quoted_node_ids: list[str],
) -> AsyncIterator[str]:
    """发送一条工作区灵感卡片事件，然后发送 done。"""
    try:
        output = await asyncio.to_thread(
            generate_workspace_output, project_id, message, quoted_node_ids
        )
        yield _sse(
            {"type": "output", "output_type": output.type, "content": output.content}
        )
    except Exception:  # noqa: BLE001
        yield _sse({"type": "error", "message": "工作区灵感生成失败，请稍后再试"})
    yield _sse({"type": "done"})
