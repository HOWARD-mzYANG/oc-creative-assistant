"""System-level HTTP routes.

These endpoints do not access business data; they are mainly used for local
connectivity confirmation and Electron/dev-script health checks.
"""

import uuid

from fastapi import APIRouter

from app.core.settings import get_web_search_settings
from app.services.web_search_client import WebSearchError, WebSearchUnavailable, search_web


router = APIRouter(tags=["system"])


_BOOT_ID = uuid.uuid4().hex


@router.get("/")
async def root() -> dict[str, str]:
    """返回 backend root route health message."""
    return {"message": "OC Creative Assistant backend is running"}


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a fixed health check structure, including a boot_id so the frontend can detect whether the backend has been restarted."""
    return {"status": "ok", "service": "backend", "boot_id": _BOOT_ID}


@router.get("/health/web-search")
async def web_search_health() -> dict[str, object]:
    """Confirm Tavily is configured and can return a live result (dev / setup check)."""
    settings = get_web_search_settings()
    if not settings.is_configured:
        return {
            "status": "unconfigured",
            "provider": settings.provider,
            "message": "Set OC_WEB_SEARCH_API_KEY in backend/.env",
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
    """Return a sample local connectivity response."""
    return {"message": f"Hello {name}"}