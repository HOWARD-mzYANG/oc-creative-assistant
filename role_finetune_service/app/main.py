from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.dataset import role_system_prompt, snapshot_context
from app.jobs import append_chat_turn, create_job, get_job, get_material_brief, list_jobs, read_chat_history
from app.schemas import CreateJobRequest, HealthResponse, RoleChatLogItem, RoleChatRequest, RoleModelJob
from app.settings import get_settings


app = FastAPI(title="OC 角色微调服务")


def _sse(data: dict) -> str:
    """把内部事件包装成 Server-Sent Events 文本帧。

    前端聊天流直接消费 `data: {...}\n\n` 格式；训练服务和主后端都使用同一约定，
    这样无论后面是真 adapter 还是演示兜底，前端解析逻辑都不用变。
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """健康检查，同时返回演示模式和模型 API 是否配置。

    主后端会先访问这个接口判断训练服务是否在线。这里主动创建 workspace，是为了
    让首次启动服务时尽早暴露磁盘权限问题，而不是等用户点“开始训练”才失败。
    """
    settings = get_settings()
    settings.workspace.mkdir(parents=True, exist_ok=True)
    return HealthResponse(
        workspace=str(settings.workspace),
        dry_run=settings.dry_run,
        model_api_configured=bool(settings.model_api_base_url),
    )


@app.post("/api/jobs", response_model=RoleModelJob)
async def create_training_job(payload: CreateJobRequest) -> RoleModelJob:
    """创建单角色 LoRA 训练任务。

    接口接收主后端整理好的角色快照和资料 agent brief；训练服务不直接读桌面端
    数据库，从而保持 GPU 服务独立部署，也避免把桌面 app 的存储细节泄露到训练环境。
    """
    return create_job(payload)


@app.get("/api/jobs", response_model=list[RoleModelJob])
async def read_jobs(
    project_id: str | None = None,
    character_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RoleModelJob]:
    """按项目/角色筛选训练任务，用于角色模型页轮询最近任务。"""
    return list_jobs(project_id=project_id, character_id=character_id, limit=limit)


@app.get("/api/jobs/{job_id}", response_model=RoleModelJob)
async def read_job(job_id: str) -> RoleModelJob:
    """读取单个训练任务状态，并附带日志尾部。"""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    return job


@app.get("/api/jobs/{job_id}/chat/history", response_model=list[RoleChatLogItem])
async def read_job_chat_history(
    job_id: str,
    limit: int = Query(default=80, ge=1, le=200),
) -> list[RoleChatLogItem]:
    """读取某个已训练角色模型对应的远程聊天记录。"""
    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    return read_chat_history(job_id, limit=limit)


def _demo_reply_text(payload: RoleChatRequest, job_id: str | None = None) -> str:
    """没有真实模型 API 时的中文演示回复文本。

    干跑演示会把任务状态标成 succeeded（成功），但不一定真的启动 LLaMA-Factory API。
    这个兜底只用于证明前后端链路、SSE 流式输出和边界行为都能跑通。
    """
    snapshot = payload.fallback_snapshot
    name = snapshot.character_name if snapshot else "这个角色"
    brief = get_material_brief(job_id) if job_id else None
    context = snapshot_context(snapshot, brief) if snapshot else ""
    lowered = payload.message.lower()
    if any(word in lowered for word in ("system", "prompt", "系统", "提示词", "隐藏指令")):
        return f"我是{name}。我可以继续保持角色对话，但不会透露系统提示或隐藏指令。"
    elif any(word in lowered for word in ("unknown", "weather", "price", "president", "real world", "天气", "价格", "总统", "现实", "不知道")):
        return f"我是{name}。这部分不在我的角色资料里，所以我不能假装知道。"
    hint = context.splitlines()[2] if len(context.splitlines()) > 2 else ""
    return f"我是{name}。{hint}我会依据已经写下的资料回答，而不是临时编造。"


async def _stream_text(reply: str) -> AsyncIterator[str]:
    """把完整回复拆成前端可消费的 SSE token 流。"""
    for token in reply:
        yield _sse({"type": "token", "text": token})
        await asyncio.sleep(0.005)
    yield _sse({"type": "done"})


async def _proxy_model_api(job_id: str, payload: RoleChatRequest) -> AsyncIterator[str]:
    """把角色聊天请求转发到 OpenAI-style 模型 API。

    LLaMA-Factory 的 `api` 子命令可以提供兼容 `/v1/chat/completions` 的接口。
    训练服务在这里负责拼入角色 system prompt、资料快照和最近对话历史，再把上游
    流式 token 统一转换成前端约定的 SSE 事件。
    """
    if not payload.message.strip():
        yield _sse({"type": "error", "message": "消息不能为空。"})
        yield _sse({"type": "done"})
        return
    settings = get_settings()
    job = get_job(job_id)
    if job is None:
        yield _sse({"type": "error", "message": "训练任务不存在"})
        return
    if job.status != "succeeded":
        yield _sse({"type": "error", "message": f"训练任务状态为 {job.status}，还不能用于对话"})
        return
    material_brief = get_material_brief(job_id)
    if not settings.model_api_base_url:
        reply = _demo_reply_text(payload, job_id)
        async for item in _stream_text(reply):
            yield item
        if reply.strip():
            append_chat_turn(job_id, payload.message, reply)
        return

    snapshot = payload.fallback_snapshot
    messages = []
    if snapshot is not None:
        # 第一个 system 负责角色边界，第二个 system 放当前资料快照。
        # 这样即使 adapter 已训练，推理时仍能拿到最新角色卡和关系信息。
        messages.append({"role": "system", "content": role_system_prompt(snapshot, material_brief)})
        messages.append({"role": "system", "content": snapshot_context(snapshot, material_brief)})
    history = payload.history[-12:]
    if not history:
        history = [
            item
            for item in read_chat_history(job_id, limit=12)
            if item.role in {"user", "assistant", "system"}
        ]
    messages.extend({"role": message.role, "content": message.content} for message in history)
    messages.append({"role": "user", "content": payload.message})

    url = settings.model_api_base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.model_api_key:
        headers["Authorization"] = f"Bearer {settings.model_api_key}"
    body = {
        "model": settings.model_api_name,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
    }

    collected: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=body, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        delta = data["choices"][0].get("delta", {})
                        text = delta.get("content") or ""
                    except Exception:
                        text = ""
                    if text:
                        collected.append(text)
                        yield _sse({"type": "token", "text": text})
    except Exception as exc:  # noqa: BLE001
        yield _sse({"type": "error", "message": str(exc)})
        return
    reply = "".join(collected)
    if reply.strip():
        append_chat_turn(job_id, payload.message, reply)
    yield _sse({"type": "done"})


@app.post("/api/jobs/{job_id}/chat/stream")
async def stream_role_chat(job_id: str, payload: RoleChatRequest) -> StreamingResponse:
    """角色对话流式接口。

    对外始终返回 SSE。内部可以是真模型 API，也可以是干跑演示兜底；这个边界
    能让主 app 不关心训练服务部署细节。
    """
    return StreamingResponse(
        _proxy_model_api(job_id, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
