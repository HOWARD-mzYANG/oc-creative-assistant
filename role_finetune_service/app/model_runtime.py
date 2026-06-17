from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.schemas import RoleModelJob
from app.settings import ServiceSettings, get_settings


# LLaMA-Factory 的 api 子命令一次只能稳定加载一套基础模型 + adapter。
# 因此前端选择不同 job 时，训练服务需要在本进程里记住“当前正在服务哪个 job”，
# 如果用户切换到另一个已完成模型，就先停掉旧 API，再启动新的 API。
_LOCK = threading.RLock()
_PROCESS: subprocess.Popen | None = None
_ACTIVE_JOB_ID: str | None = None
_ACTIVE_BASE_URL: str | None = None
_ACTIVE_CONFIG_PATH: Path | None = None
_ACTIVE_LOG_PATH: Path | None = None


def _job_dir(job: RoleModelJob, settings: ServiceSettings) -> Path:
    """推导 job 的工作目录。

    新任务会在 `adapter_path` 里保存绝对路径；旧任务或异常任务可能没有这个字段，
    所以这里保留 `workspace/jobs/{job_id}` 作为兜底。所有运行时配置和 API 日志都写回
    job 目录，方便 AutoDL 上直接按任务排查。
    """
    if job.adapter_path:
        return Path(job.adapter_path).expanduser().resolve().parent
    return (settings.workspace / "jobs" / job.id).expanduser().resolve()


def _adapter_dir(job: RoleModelJob, settings: ServiceSettings) -> Path:
    """返回当前 job 的 adapter 目录，并尽量兼容旧 job 记录。"""
    if job.adapter_path:
        return Path(job.adapter_path).expanduser().resolve()
    return _job_dir(job, settings) / "adapter"


def _api_base_url(settings: ServiceSettings) -> str:
    """得到训练服务访问模型 API 的地址。

    `ROLE_MODEL_API_HOST` 是给 LLaMA-Factory 绑定 socket 用的，常见值是 127.0.0.1 或
    0.0.0.0；但本服务访问它时最好始终走一个明确 URL。因此如果用户没有设置
    `ROLE_MODEL_API_BASE_URL`，就默认访问本机 127.0.0.1:{port}。
    """
    if settings.model_api_base_url:
        return settings.model_api_base_url.rstrip("/")
    return f"http://127.0.0.1:{settings.model_api_port}"


def _read_tail(path: Path | None, limit: int = 4000) -> str:
    """读取模型 API 日志尾部，用于启动失败时返回可诊断的错误。"""
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def _is_process_alive(process: subprocess.Popen | None) -> bool:
    """判断托管的 LLaMA-Factory API 子进程是否仍在运行。"""
    return process is not None and process.poll() is None


def _api_responds(base_url: str) -> bool:
    """探测 OpenAI-style API 是否已经可以接收请求。

    LLaMA-Factory API 通常提供 `/v1/models`。这里不强依赖返回 200，只要服务端已经能
    给出 HTTP 响应，就说明端口和 ASGI 服务已起来，后续真正的聊天请求可以进入上游。
    """
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/models", timeout=2.0)
        return response.status_code < 500
    except Exception:
        return False


def _write_api_config(job: RoleModelJob, settings: ServiceSettings) -> Path:
    """为当前 job 生成 LLaMA-Factory API 配置。

    训练阶段的 `train.yaml` 负责产出 adapter；推理阶段需要一份更小的配置，只声明基础模型、
    adapter、模板和 LoRA 类型。配置放在 job 目录下，用户可以直接打开检查当前加载的到底
    是哪个角色模型。
    """
    adapter_dir = _adapter_dir(job, settings)
    if not adapter_dir.exists():
        raise RuntimeError(
            f"找不到 adapter 目录：{adapter_dir}。请确认训练不是 dry-run，且任务已经真实成功。"
        )
    if not (adapter_dir / "adapter_config.json").exists():
        raise RuntimeError(
            f"adapter 目录缺少 adapter_config.json：{adapter_dir}。这通常表示训练没有真正产出 LoRA。"
        )

    config: dict[str, Any] = {
        "model_name_or_path": settings.base_model,
        "adapter_name_or_path": str(adapter_dir),
        "template": "qwen",
        "finetuning_type": "lora",
        "trust_remote_code": True,
    }
    path = _job_dir(job, settings) / "chat_api.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _stop_process_locked() -> None:
    """停止当前托管的模型 API 子进程。

    这个函数要求调用方已经拿到 `_LOCK`。切换角色模型时必须先释放 GPU 显存，再启动新
    adapter，否则 3090 这类单卡环境很容易因为两个模型同时加载而 OOM。
    """
    global _PROCESS, _ACTIVE_JOB_ID, _ACTIVE_BASE_URL, _ACTIVE_CONFIG_PATH, _ACTIVE_LOG_PATH

    if _PROCESS is not None and _PROCESS.poll() is None:
        _PROCESS.terminate()
        try:
            _PROCESS.wait(timeout=20)
        except subprocess.TimeoutExpired:
            _PROCESS.kill()
            _PROCESS.wait(timeout=10)
    _PROCESS = None
    _ACTIVE_JOB_ID = None
    _ACTIVE_BASE_URL = None
    _ACTIVE_CONFIG_PATH = None
    _ACTIVE_LOG_PATH = None


def stop_model_api() -> None:
    """公开的停止函数，供 FastAPI 关闭事件或手动测试调用。"""
    with _LOCK:
        _stop_process_locked()


def _start_process_locked(job: RoleModelJob, settings: ServiceSettings, base_url: str) -> None:
    """启动加载当前 job adapter 的 LLaMA-Factory API。

    这里直接复用 `ROLE_LLAMAFACTORY_BIN`，所以用户只需要把它指向当前 conda 环境里的
    `llamafactory-cli`。stdout/stderr 会写入 `api.log`，避免模型加载日志刷到 uvicorn 主
    日志里，也方便启动失败时把最后几 KB 返回给前端。
    """
    global _PROCESS, _ACTIVE_JOB_ID, _ACTIVE_BASE_URL, _ACTIVE_CONFIG_PATH, _ACTIVE_LOG_PATH

    config_path = _write_api_config(job, settings)
    log_path = _job_dir(job, settings) / "api.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["API_HOST"] = settings.model_api_host
    env["API_PORT"] = str(settings.model_api_port)

    command = [settings.llamafactory_bin, "api", str(config_path)]
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[角色微调] 启动模型 API，job={job.id}，adapter={_adapter_dir(job, settings)}\n")
        log.write("[角色微调] 执行命令：" + " ".join(command) + "\n")
        log.flush()
        _PROCESS = subprocess.Popen(
            command,
            cwd=str(settings.llamafactory_dir or _job_dir(job, settings)),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

    _ACTIVE_JOB_ID = job.id
    _ACTIVE_BASE_URL = base_url
    _ACTIVE_CONFIG_PATH = config_path
    _ACTIVE_LOG_PATH = log_path


def _wait_until_ready_locked(settings: ServiceSettings, base_url: str) -> None:
    """等待模型 API 完成加载。

    LLaMA-Factory 第一次加载基础模型和 adapter 可能需要几十秒。这个等待发生在线程池中，
    不会卡住 uvicorn 事件循环；如果子进程提前退出或超时，会把 `api.log` 尾部拼进错误，
    让前端能直接看到是路径、显存还是依赖问题。
    """
    deadline = time.time() + settings.model_api_startup_timeout
    while time.time() < deadline:
        if not _is_process_alive(_PROCESS):
            tail = _read_tail(_ACTIVE_LOG_PATH)
            raise RuntimeError(f"模型 API 启动后立即退出。\n{tail}")
        if _api_responds(base_url):
            return
        time.sleep(2)
    tail = _read_tail(_ACTIVE_LOG_PATH)
    raise RuntimeError(f"模型 API 启动超时，超过 {settings.model_api_startup_timeout}s 未就绪。\n{tail}")


def ensure_model_api(job: RoleModelJob) -> str:
    """确保当前选中的 job 已经被加载为可访问的模型 API，并返回 API base URL。

    - `ROLE_MODEL_API_AUTO_START=false` 时，不管理子进程，只返回用户配置的固定
      `ROLE_MODEL_API_BASE_URL`。
    - 自动模式下，如果当前已加载的 job 和请求 job 一致且 API 仍有响应，直接复用。
    - 如果用户切换模型，先停旧进程释放显存，再用新 job 的 adapter 重新启动 API。
    """
    settings = get_settings()
    if not settings.model_api_auto_start:
        if settings.model_api_base_url:
            return settings.model_api_base_url.rstrip("/")
        raise RuntimeError("未配置 ROLE_MODEL_API_BASE_URL，且 ROLE_MODEL_API_AUTO_START=false。")

    base_url = _api_base_url(settings)
    with _LOCK:
        if _ACTIVE_JOB_ID == job.id and _is_process_alive(_PROCESS) and _api_responds(base_url):
            return base_url

        if _PROCESS is not None:
            _stop_process_locked()

        _start_process_locked(job, settings, base_url)
        try:
            _wait_until_ready_locked(settings, base_url)
        except Exception:
            _stop_process_locked()
            raise
        return base_url


def get_runtime_status() -> dict[str, Any]:
    """返回当前模型 API 运行状态，供 `/health` 暴露给主后端和调试命令。"""
    with _LOCK:
        return {
            "active_model_job_id": _ACTIVE_JOB_ID,
            "active_model_api_url": _ACTIVE_BASE_URL,
            "active_model_api_pid": _PROCESS.pid if _is_process_alive(_PROCESS) else None,
            "active_model_api_config": str(_ACTIVE_CONFIG_PATH) if _ACTIVE_CONFIG_PATH else None,
            "active_model_api_log": str(_ACTIVE_LOG_PATH) if _ACTIVE_LOG_PATH else None,
        }
