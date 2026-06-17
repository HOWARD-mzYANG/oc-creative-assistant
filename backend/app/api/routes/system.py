"""系统级 HTTP 路由。

这些端点不访问业务数据，主要用于本地连通性确认，以及 Electron / 开发脚本健康检查。
"""

import uuid

from fastapi import APIRouter

from app.core.settings import get_web_search_settings
from app.services.web_search_client import WebSearchError, WebSearchUnavailable, search_web


router = APIRouter(tags=["system"])


_BOOT_ID = uuid.uuid4().hex


@router.get("/")
async def root() -> dict[str, str]:
    """返回后端根路由健康提示。"""
    return {"message": "OC Creative Assistant 后端正在运行"}


@router.get("/health")
async def health() -> dict[str, str]:
    """返回固定健康检查结构；boot_id 用于前端判断后端是否重启。"""
    return {"status": "ok", "service": "backend", "boot_id": _BOOT_ID}


@router.get("/health/web-search")
async def web_search_health() -> dict[str, object]:
    """确认 Tavily 已配置且能返回实时结果（开发 / 安装检查）。"""
    settings = get_web_search_settings()
    if not settings.is_configured:
        return {
            "status": "unconfigured",
            "provider": settings.provider,
            "message": "请在 backend/.env 中设置 OC_WEB_SEARCH_API_KEY",
        }
    try:
        probe = search_web("test connectivity", top_k=1)
        return {
            "status": "ok",
            "provider": settings.provider,
            "sample_answer_len": len(probe.answer or ""),
            "hits": len(probe.hits),
        }
    except WebSearchUnavailable as exc:
        return {"status": "unavailable", "provider": settings.provider, "message": str(exc)}
    except WebSearchError as exc:
        return {"status": "error", "provider": settings.provider, "message": str(exc)}


@router.get("/hello/{name}")
async def say_hello(name: str) -> dict[str, str]:
    """返回一个本地连通性示例响应。"""
    return {"message": f"你好，{name}"}
