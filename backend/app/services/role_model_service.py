"""Project-scoped OC role model service.

This module keeps the role-model feature portable: model download, LoRA
training, and local inference are optional runtime capabilities. The FastAPI
app can still start on machines without CUDA, PyTorch, ModelScope, transformers,
or PEFT; those missing capabilities are surfaced as job states instead of import
errors at startup.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.paths import DATA_DIR
from app.db.database import SessionLocal
from app.db.models import EdgeORM, NodeORM, ProjectORM
from app.llm.factory import get_llm_provider
from app.rag.retrieval import build_project_vector_context, merge_context
from app.schemas import (
    RoleModelChatMessagePayload,
    RoleModelChatHistoryItemPayload,
    RoleModelChatRequest,
    RoleModelChatResponse,
    RoleModelDatasetPayload,
    RoleModelDatasetGenerateRequest,
    RoleModelDatasetSamplePayload,
    RoleModelDatasetUpdateRequest,
    RoleModelDownloadRequest,
    RoleModelGpuPayload,
    RoleModelHardwarePayload,
    RoleModelJobPayload,
    RoleModelRecommendationPayload,
    RoleModelRecommendationRequest,
    RoleModelStatePayload,
    RoleModelTrainRequest,
)
from app.services.graph_mappers import db_fields_to_api
from app.services.graph_repository import require_project


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ROLE_MODEL_ROOT = DATA_DIR / "role_models"
_DATASET_MIN_TRAINING_SAMPLES = 200
_DATASET_MAX_GENERATED_SAMPLES = 800
_DATASET_MAX_SAMPLES_PER_CHARACTER = 240
_THREAD_LOCK = threading.Lock()
_RUNNING_THREADS: dict[tuple[str, str], threading.Thread] = {}
_LOCAL_RUNTIME_CACHE: dict[str, Any] = {}
_ROLE_CHAT_HISTORY_LIMIT = 16
_ROLE_CHAT_FILE_PREFIX = "role-chat"


_MODEL_CANDIDATES: list[dict[str, Any]] = [
    {
        "model_id": "Qwen/Qwen3-0.6B",
        "display_name": "Qwen3 0.6B",
        "parameter_count_b": 0.6,
        "estimated_vram_gb": 4.0,
        "context_length": 4096,
    },
    {
        "model_id": "Qwen/Qwen3-1.7B",
        "display_name": "Qwen3 1.7B",
        "parameter_count_b": 1.7,
        "estimated_vram_gb": 7.0,
        "context_length": 4096,
    },
    {
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "display_name": "Qwen2.5 1.5B Instruct",
        "parameter_count_b": 1.5,
        "estimated_vram_gb": 6.5,
        "context_length": 4096,
    },
    {
        "model_id": "Qwen/Qwen2.5-3B-Instruct",
        "display_name": "Qwen2.5 3B Instruct",
        "parameter_count_b": 3.0,
        "estimated_vram_gb": 11.0,
        "context_length": 4096,
    },
]


class _DatasetGenerationOutput(BaseModel):
    samples: list[RoleModelDatasetSamplePayload] = Field(default_factory=list)


class _RecommendationOutput(BaseModel):
    model_id: str
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    lora_rank: int = 8
    lora_alpha: int = 16
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    max_seq_length: int = 1024
    learning_rate: float = 0.0002


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_project_dir(project_id: str) -> Path:
    """Return a project-scoped directory under DATA_DIR, never outside it."""
    safe_id = "".join(ch for ch in project_id if ch.isalnum() or ch in "-_")
    if not safe_id:
        raise ValueError("Invalid project id")
    root = _ROLE_MODEL_ROOT.resolve()
    candidate = (root / safe_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Invalid project role-model path") from exc
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _project_dir_checked(project_id: str) -> Path:
    with SessionLocal() as db:
        require_project(db, project_id)
    return _safe_project_dir(project_id)


def _json_path(project_id: str, name: str) -> Path:
    return _project_dir_checked(project_id) / name


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _modelscope_url(model_id: str) -> str:
    return f"https://modelscope.cn/models/{model_id}/summary"


def _validate_model_id(model_id: str) -> str:
    cleaned = model_id.strip()
    if not _MODEL_ID_RE.match(cleaned):
        raise ValueError("ModelScope model_id must look like 'namespace/model-name'")
    return cleaned


def _role_chat_file_key(character_name: str) -> str:
    digest = hashlib.sha256(character_name.strip().casefold().encode("utf-8")).hexdigest()[:24]
    return f"{_ROLE_CHAT_FILE_PREFIX}-{digest}.json"


def _role_chat_history_path(project_id: str, character_name: str) -> Path:
    return _project_dir_checked(project_id) / "chat" / _role_chat_file_key(character_name)


def _project_role_names(project_id: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    dataset = get_dataset(project_id)
    for sample in dataset.samples:
        name = sample.character_name.strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    profiles, _ = _character_profiles(project_id)
    for profile in profiles:
        name = str(profile.get("name") or "").strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _normalize_chat_character(project_id: str, character_name: str | None) -> str:
    requested = (character_name or "").strip()
    if not requested:
        raise ValueError("请先选择一个角色，再开始角色模型聊天。")
    names = _project_role_names(project_id)
    if not names:
        raise ValueError("当前项目还没有可聊天角色，请先创建角色并生成/保存 LoRA 数据集。")
    for name in names:
        if name == requested:
            return name
    for name in names:
        if name.casefold() == requested.casefold():
            return name
    raise ValueError("请选择数据集或角色卡中已有的角色。")


def _parse_chat_created_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _chat_history_item(data: dict[str, Any], character_name: str) -> RoleModelChatHistoryItemPayload | None:
    role = data.get("role")
    content = str(data.get("content") or "")
    if role not in {"user", "assistant"} or not content:
        return None
    cited_node_ids = data.get("cited_node_ids")
    if not isinstance(cited_node_ids, list):
        cited_node_ids = []
    retrieved_context = data.get("retrieved_context")
    if not isinstance(retrieved_context, list):
        retrieved_context = []
    return RoleModelChatHistoryItemPayload(
        id=str(data.get("id") or f"rolemsg-{uuid4().hex}"),
        role=role,
        content=content,
        mode=str(data.get("mode") or ""),
        warning=str(data.get("warning") or ""),
        character_name=character_name,
        cited_node_ids=[str(item) for item in cited_node_ids],
        retrieved_context=[item for item in retrieved_context if isinstance(item, dict)],
        created_at=_parse_chat_created_at(data.get("created_at")),
    )


def get_role_model_chat_history(
    project_id: str,
    character_name: str | None,
) -> list[RoleModelChatHistoryItemPayload]:
    """Read persisted role-model chat history for one character only."""
    character = _normalize_chat_character(project_id, character_name)
    path = _role_chat_history_path(project_id, character)
    data = _read_json(path, {"messages": []})
    raw_messages = data.get("messages") if isinstance(data, dict) else []
    if not isinstance(raw_messages, list):
        return []
    items = [_chat_history_item(item, character) for item in raw_messages if isinstance(item, dict)]
    return [item for item in items if item is not None]


def clear_role_model_chat_history(project_id: str, character_name: str | None) -> None:
    """Delete persisted role-model chat history for one character only."""
    character = _normalize_chat_character(project_id, character_name)
    path = _role_chat_history_path(project_id, character)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _persist_role_model_chat_turn(
    project_id: str,
    request: RoleModelChatRequest,
    response: RoleModelChatResponse,
) -> None:
    character = _normalize_chat_character(project_id, request.character_name)
    path = _role_chat_history_path(project_id, character)
    data = _read_json(path, {"character_name": character, "messages": []})
    messages = data.get("messages") if isinstance(data, dict) else []
    if not isinstance(messages, list):
        messages = []
    now = datetime.now(timezone.utc)
    messages.extend(
        [
            {
                "id": f"rolemsg-{uuid4().hex}",
                "role": "user",
                "content": request.message,
                "character_name": character,
                "created_at": now.isoformat(),
            },
            {
                "id": f"rolemsg-{uuid4().hex}",
                "role": "assistant",
                "content": response.reply,
                "character_name": character,
                "mode": response.mode,
                "warning": response.warning,
                "cited_node_ids": response.cited_node_ids,
                "retrieved_context": response.retrieved_context,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
    )
    _write_json(
        path,
        {
            "character_name": character,
            "updated_at": _now(),
            "messages": messages[-400:],
        },
    )


def _request_with_persisted_history(
    project_id: str,
    request: RoleModelChatRequest,
) -> RoleModelChatRequest:
    character = _normalize_chat_character(project_id, request.character_name)
    persisted = get_role_model_chat_history(project_id, character)
    if persisted:
        history = [
            RoleModelChatMessagePayload(role=item.role, content=item.content)
            for item in persisted[-_ROLE_CHAT_HISTORY_LIMIT:]
        ]
    else:
        history = [
            item
            for item in request.history[-_ROLE_CHAT_HISTORY_LIMIT:]
            if item.role in {"user", "assistant"}
        ]
    return RoleModelChatRequest(
        message=request.message,
        character_name=character,
        history=history,
    )


def _memory_windows() -> tuple[float, float]:
    """Return total/available RAM in GiB on Windows without psutil."""

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0.0, 0.0
    return (
        round(status.ullTotalPhys / (1024**3), 2),
        round(status.ullAvailPhys / (1024**3), 2),
    )


def _memory_posix() -> tuple[float, float]:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        total = page_size * pages
        available = 0
        if sys.platform.startswith("linux"):
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            for line in meminfo.splitlines():
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
                    break
        return round(total / (1024**3), 2), round(available / (1024**3), 2)
    except Exception:
        return 0.0, 0.0


def _detect_torch_gpus() -> tuple[list[RoleModelGpuPayload], bool]:
    try:
        import torch  # type: ignore
    except Exception:
        return [], False
    if not torch.cuda.is_available():
        return [], False
    gpus: list[RoleModelGpuPayload] = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        gpus.append(
            RoleModelGpuPayload(
                name=props.name,
                memory_gb=round(props.total_memory / (1024**3), 2),
                backend="cuda",
                available=True,
            )
        )
    return gpus, bool(gpus)


def _detect_nvidia_smi_gpus() -> list[RoleModelGpuPayload]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    gpus: list[RoleModelGpuPayload] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            memory_gb = round(float(parts[1]) / 1024, 2)
        except ValueError:
            memory_gb = 0.0
        gpus.append(
            RoleModelGpuPayload(
                name=parts[0],
                memory_gb=memory_gb,
                backend="nvidia-smi",
                available=memory_gb > 0,
            )
        )
    return gpus


def inspect_hardware(project_id: str) -> RoleModelHardwarePayload:
    """Inspect host capabilities with graceful fallbacks."""
    project_dir = _project_dir_checked(project_id)
    if platform.system().lower().startswith("windows"):
        ram_total, ram_available = _memory_windows()
    else:
        ram_total, ram_available = _memory_posix()

    disk = shutil.disk_usage(project_dir)
    gpus, has_torch_cuda = _detect_torch_gpus()
    if not gpus:
        gpus = _detect_nvidia_smi_gpus()
    best_vram = max((gpu.memory_gb for gpu in gpus), default=0.0)
    has_nvidia_gpu = any(gpu.backend in {"cuda", "nvidia-smi"} for gpu in gpus)
    has_cuda = has_torch_cuda or has_nvidia_gpu

    notes: list[str] = []
    if has_nvidia_gpu and not has_torch_cuda:
        notes.append("检测到 NVIDIA GPU，但当前 PyTorch 未启用 CUDA；本地 LoRA 训练需要安装匹配 CUDA 的 torch。")
    if not has_cuda:
        notes.append("未检测到可用 CUDA GPU；可编辑数据集和使用 API 兜底聊天，但本地 LoRA 训练通常不可行。")
    if best_vram and best_vram < 6:
        notes.append("检测到 GPU 显存低于 6GB，建议选择 0.6B 级别模型并降低序列长度。")
    if ram_total and ram_total < 12:
        notes.append("系统内存较小，训练时请关闭其他程序。")
    disk_free_gb = round(disk.free / (1024**3), 2)
    if disk_free_gb < 12:
        notes.append("磁盘剩余空间不足 12GB，可能无法下载基础模型或保存 LoRA 权重。")

    can_train = has_torch_cuda and best_vram >= 6 and disk_free_gb >= 12
    hardware = RoleModelHardwarePayload(
        os=f"{platform.system()} {platform.release()}",
        python=platform.python_version(),
        cpu_count=os.cpu_count() or 0,
        ram_total_gb=ram_total,
        ram_available_gb=ram_available,
        disk_free_gb=disk_free_gb,
        gpus=gpus,
        has_cuda=has_cuda,
        can_train_lora=can_train,
        notes=notes,
    )
    _write_json(project_dir / "hardware.json", hardware.model_dump())
    return hardware


def _candidate_by_id(model_id: str) -> dict[str, Any] | None:
    for candidate in _MODEL_CANDIDATES:
        if candidate["model_id"] == model_id:
            return candidate
    return None


def _heuristic_recommendation(
    hardware: RoleModelHardwarePayload,
    preferred_model_id: str | None = None,
) -> RoleModelRecommendationPayload:
    best_vram = max((gpu.memory_gb for gpu in hardware.gpus), default=0.0)
    if preferred_model_id:
        candidate = _candidate_by_id(preferred_model_id) or {
            "model_id": preferred_model_id,
            "display_name": preferred_model_id.split("/")[-1],
            "parameter_count_b": 0.0,
            "estimated_vram_gb": 8.0,
            "context_length": 4096,
        }
    elif not hardware.has_cuda or best_vram < 6:
        candidate = _MODEL_CANDIDATES[0]
    elif best_vram < 10:
        candidate = _MODEL_CANDIDATES[1]
    else:
        candidate = _MODEL_CANDIDATES[3]

    warnings = list(hardware.notes)
    if not hardware.can_train_lora:
        warnings.append("当前主机可能无法完成真实 LoRA 训练；功能会保留数据集与 API 兜底聊天。")

    return RoleModelRecommendationPayload(
        model_id=candidate["model_id"],
        display_name=candidate["display_name"],
        parameter_count_b=float(candidate.get("parameter_count_b") or 0.0),
        estimated_vram_gb=float(candidate.get("estimated_vram_gb") or 0.0),
        context_length=int(candidate.get("context_length") or 4096),
        lora_rank=8 if best_vram < 12 else 16,
        lora_alpha=16 if best_vram < 12 else 32,
        batch_size=1,
        gradient_accumulation_steps=12 if best_vram < 8 else 8,
        max_seq_length=768 if best_vram < 8 else 1024,
        learning_rate=0.0002,
        download_url=_modelscope_url(candidate["model_id"]),
        reason="根据显存、内存和磁盘空间选择尽量小且适合角色语气 LoRA 的模型。",
        warnings=warnings,
    )


def recommend_model(
    project_id: str,
    payload: RoleModelRecommendationRequest,
) -> RoleModelRecommendationPayload:
    """Use the configured AI provider to refine a safe heuristic recommendation."""
    hardware = inspect_hardware(project_id)
    preferred = _validate_model_id(payload.preferred_model_id) if payload.preferred_model_id else None
    fallback = _heuristic_recommendation(hardware, preferred)

    system = (
        "你是本地大模型部署顾问。请只从候选 ModelScope 模型中选择一个，"
        "目标是在普通个人电脑上尽量稳地训练 OC 角色 LoRA。不要推荐超出硬件能力的模型。"
    )
    candidate_block = json.dumps(_MODEL_CANDIDATES, ensure_ascii=False)
    user = (
        f"[硬件]\n{hardware.model_dump_json()}\n\n"
        f"[候选模型]\n{candidate_block}\n\n"
        f"[用户偏好]\nmodel_id={preferred or '(none)'}; target_character={payload.target_character or '(none)'}\n\n"
        "输出字段必须给出 model_id、reason、warnings、lora_rank、lora_alpha、batch_size、"
        "gradient_accumulation_steps、max_seq_length、learning_rate。"
    )
    try:
        out = get_llm_provider().structured(
            [SystemMessage(content=system), HumanMessage(content=user)],
            _RecommendationOutput,
        )
    except Exception:
        out = None

    if out is None:
        recommendation = fallback
    else:
        candidate = _candidate_by_id(out.model_id) or _candidate_by_id(fallback.model_id)
        if candidate is None:
            candidate = _MODEL_CANDIDATES[0]
        recommendation = RoleModelRecommendationPayload(
            model_id=candidate["model_id"],
            display_name=candidate["display_name"],
            parameter_count_b=float(candidate["parameter_count_b"]),
            estimated_vram_gb=float(candidate["estimated_vram_gb"]),
            context_length=int(candidate["context_length"]),
            lora_rank=max(4, min(int(out.lora_rank), 64)),
            lora_alpha=max(8, min(int(out.lora_alpha), 128)),
            batch_size=max(1, min(int(out.batch_size), 8)),
            gradient_accumulation_steps=max(1, min(int(out.gradient_accumulation_steps), 64)),
            max_seq_length=max(256, min(int(out.max_seq_length), 4096)),
            learning_rate=max(0.00001, min(float(out.learning_rate), 0.001)),
            download_url=_modelscope_url(candidate["model_id"]),
            reason=out.reason or fallback.reason,
            warnings=[*hardware.notes, *out.warnings],
        )

    _write_json(_json_path(project_id, "hardware.json"), hardware.model_dump())
    _write_json(_json_path(project_id, "recommendation.json"), recommendation.model_dump())
    return recommendation


def get_recommendation(project_id: str) -> RoleModelRecommendationPayload | None:
    data = _read_json(_json_path(project_id, "recommendation.json"), None)
    return RoleModelRecommendationPayload.model_validate(data) if data else None


def _character_profiles(project_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with SessionLocal() as db:
        require_project(db, project_id)
        nodes = list(
            db.scalars(
                select(NodeORM)
                .where(NodeORM.project_id == project_id)
                .order_by(NodeORM.sort_order, NodeORM.created_at)
            )
        )
        edges = list(
            db.scalars(
                select(EdgeORM)
                .where(EdgeORM.project_id == project_id)
                .order_by(EdgeORM.sort_order, EdgeORM.created_at)
            )
        )

    node_by_id = {node.id: node for node in nodes}
    profiles: list[dict[str, Any]] = []
    for node in nodes:
        if node.node_type != "character":
            continue
        related: list[str] = []
        for edge in edges:
            other_id = ""
            if edge.source == node.id:
                other_id = edge.target
            elif edge.target == node.id:
                other_id = edge.source
            if other_id and other_id in node_by_id:
                related.append(f"{edge.label or edge.relation_type}: {node_by_id[other_id].title}")
        profiles.append(
            {
                "id": node.id,
                "name": node.title,
                "content": node.content,
                "fields": db_fields_to_api(node.meta),
                "related": related[:8],
            }
        )

    project_context = [
        {
            "id": node.id,
            "type": node.node_type,
            "title": node.title,
            "content": node.content[:500],
        }
        for node in nodes
        if node.node_type != "character"
    ][:40]
    return profiles, project_context


def _sample_id(character_name: str, instruction: str, output: str) -> str:
    digest = hashlib.sha1(
        f"{character_name}\n{instruction}\n{output}".encode("utf-8")
    ).hexdigest()[:12]
    return f"sample-{digest}"


def _fallback_samples(project_id: str) -> list[RoleModelDatasetSamplePayload]:
    profiles, context = _character_profiles(project_id)
    if not profiles:
        return [
            RoleModelDatasetSamplePayload(
                id="sample-empty-project",
                character_name="旁白",
                instruction="介绍一下这个 OC 项目当前的状态。",
                input="",
                output="目前项目里还没有角色卡。可以先创建角色、世界观或剧情节点，再生成更贴合角色的训练样本。",
                tags=["fallback"],
                source_node_ids=[],
            )
        ]

    samples: list[RoleModelDatasetSamplePayload] = []
    world_hint = "；".join(item["title"] for item in context[:5])
    for profile in profiles:
        name = profile["name"]
        fields = profile.get("fields") or {}
        field_text = "；".join(f"{k}: {v}" for k, v in fields.items())
        base = (profile.get("content") or field_text or "这个角色还没有详细介绍。").strip()
        prompts = [
            (
                f"你是谁？请用{name}的口吻介绍自己。",
                "",
                f"我是{name}。{base}",
                ["self-intro"],
            ),
            (
                f"{name}在意什么？",
                "",
                f"对我来说，最重要的是那些定义我选择的经历。{base}",
                ["motivation"],
            ),
            (
                f"如果有人问起你的世界，你会怎么说？",
                "",
                f"我所处的世界并不只是背景，它会逼着每个人做选择。{world_hint or base}",
                ["world"],
            ),
            (
                f"用一段对话表现{name}的说话方式。",
                "用户：你现在打算怎么办？",
                f"{name}：我会先弄清楚自己真正想守住什么，然后再决定要付出什么代价。",
                ["voice"],
            ),
        ]
        for instruction, input_text, output, tags in prompts:
            samples.append(
                RoleModelDatasetSamplePayload(
                    id=_sample_id(name, instruction, output),
                    character_name=name,
                    instruction=instruction,
                    input=input_text,
                    output=output,
                    tags=tags,
                    source_node_ids=[profile["id"]],
                )
            )
    return samples


def _dataset_generation_targets(
    payload: RoleModelDatasetGenerateRequest | None,
    character_count: int,
) -> tuple[int, int]:
    request = payload or RoleModelDatasetGenerateRequest()
    per_character = max(8, min(int(request.samples_per_character), _DATASET_MAX_SAMPLES_PER_CHARACTER))
    requested_total = max(_DATASET_MIN_TRAINING_SAMPLES, min(int(request.max_samples), _DATASET_MAX_GENERATED_SAMPLES))
    if character_count <= 0:
        return per_character, min(requested_total, 24)
    target_total = min(requested_total, character_count * per_character)
    target_total = max(_DATASET_MIN_TRAINING_SAMPLES, target_total, min(character_count, _DATASET_MAX_GENERATED_SAMPLES))
    target_total = min(target_total, _DATASET_MAX_GENERATED_SAMPLES)
    per_character = max(
        1,
        min(
            _DATASET_MAX_SAMPLES_PER_CHARACTER,
            (target_total + character_count - 1) // character_count,
        ),
    )
    return per_character, target_total


def _profile_base_text(profile: dict[str, Any]) -> str:
    fields = profile.get("fields") or {}
    field_text = "；".join(f"{key}: {value}" for key, value in fields.items() if str(value).strip())
    return (profile.get("content") or field_text or "这个角色还没有详细介绍。").strip()


def _supplemental_samples(
    profiles: list[dict[str, Any]],
    context: list[dict[str, Any]],
    samples_per_character: int,
) -> list[RoleModelDatasetSamplePayload]:
    world_hint = "；".join(item["title"] for item in context[:6]) or "当前项目世界观"
    scene_templates = [
        (
            "self-intro",
            "请用{name}自己的口吻介绍自己，不要像设定说明。",
            "",
            "我是{name}。{base}\n{nuance}如果你想理解我，别只看我的身份，要看我在关键时刻会守住什么。",
        ),
        (
            "motivation",
            "{name}真正想要的是什么？",
            "",
            "我想要的从来不是一句漂亮话能概括的。{base}\n{nuance}我会把这件事藏在行动里，而不是反复解释给旁人听。",
        ),
        (
            "boundary",
            "如果有人要求{name}做违背本心的事，{name}会怎么回答？",
            "对方语气很强硬，希望角色立刻妥协。",
            "我可以听完你的理由，但不代表我会照做。{nuance}有些界线一旦退开，就再也不像自己了。",
        ),
        (
            "conflict",
            "写一段{name}在冲突中的回应。",
            "对方质疑角色的决定，并把局势推向僵持。",
            "你可以质疑我，但别把犹豫误认成软弱。{nuance}我做这个决定，是因为我已经看见了不做决定的代价。",
        ),
        (
            "trust",
            "{name}会怎样表达信任？",
            "",
            "信任不是把后背随便交出去。{nuance}如果我愿意相信你，那是因为我把你的选择也算进了我的未来。",
        ),
        (
            "fear",
            "{name}最害怕什么？请用角色口吻回答。",
            "",
            "我怕的不是输。{nuance}我怕的是到了最后才发现，自己为了赢，把真正不能失去的东西也交出去了。",
        ),
        (
            "memory",
            "让{name}讲一个和世界观有关的记忆。",
            "当前世界/剧情线索：{world}",
            "我记得{world}。那不是背景板，它会逼人选择，也会让人明白自己到底站在哪一边。",
        ),
        (
            "relationship",
            "{name}如何评价自己和其他角色的关系？",
            "相关关系：{related}",
            "关系从来不是写在纸上的称呼。{related}。{nuance}真正重要的是，当事情变糟时，谁还愿意留下来。",
        ),
        (
            "apology",
            "{name}做错事后会怎样道歉？",
            "",
            "我不会把道歉说得很轻。{nuance}如果是我的错，我会承认；但承认之后，我还得把它补回来。",
        ),
        (
            "refusal",
            "写一段{name}拒绝别人请求的对白。",
            "请求看似合理，但会伤害角色珍视的东西。",
            "不行。不是因为我不理解你的处境，而是因为我太理解这一步之后会发生什么。{nuance}",
        ),
        (
            "comfort",
            "{name}会怎样安慰一个陷入自责的人？",
            "",
            "别急着把所有错都揽到自己身上。{nuance}人会在混乱里做出不完整的选择，但这不代表你只能停在那一刻。",
        ),
        (
            "anger",
            "{name}生气时会怎么说话？",
            "对方触碰了角色底线。",
            "你最好现在停下。{nuance}我不想把话说得更难听，但你已经越过了我能忍受的地方。",
        ),
        (
            "choice",
            "让{name}在两个艰难选择之间做决定。",
            "两个选择都需要付出代价。",
            "没有干净的选择。{nuance}所以我会选那个让我明天还能直视自己的答案，哪怕它更痛。",
        ),
        (
            "secret",
            "{name}被问到秘密时会怎样回避？",
            "",
            "有些事我还不能告诉你。{nuance}不是因为我不信任你，而是因为说出口以后，你也会被卷进来。",
        ),
        (
            "plan",
            "{name}制定计划时会怎么表达？",
            "局势紧张，时间不多。",
            "先别慌。{nuance}把能确认的事排出来，把不能确认的风险留出余地，然后我们再决定谁往前走。",
        ),
        (
            "challenge",
            "用户质疑{name}不像自己，角色会怎么回应？",
            "",
            "你看到的只是我现在这一面。{base}\n{nuance}人不是永远用同一种语气活着，但核心的东西不会轻易变。",
        ),
        (
            "promise",
            "{name}会怎样许下承诺？",
            "",
            "我不会轻易保证。{nuance}但如果我说了会做到，那这句话就不只是安慰你，也是拴住我自己的绳结。",
        ),
        (
            "doubt",
            "{name}动摇时会怎么说？",
            "",
            "我也会怀疑。{nuance}只是怀疑不代表停下，它提醒我再看一眼自己为什么走到这里。",
        ),
        (
            "scene-dialogue",
            "写一段{name}和用户的短对白，体现角色语气。",
            "用户：你现在还相信这个计划吗？",
            "相信，但不是盲信。{nuance}如果它开始偏离我们要保护的东西，我会第一个把它改掉。",
        ),
        (
            "worldview",
            "{name}如何看待这个世界？",
            "世界/剧情线索：{world}",
            "这个世界不会因为谁心软就停下来。{nuance}可正因为如此，人才更要决定自己不愿意变成什么样。",
        ),
        (
            "help",
            "{name}会怎样请求帮助？",
            "",
            "我需要你帮我。{nuance}这句话对我来说并不容易，但现在逞强只会让局势更糟。",
        ),
        (
            "lonely",
            "{name}独处时会说什么？",
            "",
            "安静下来以后，很多声音反而更清楚。{nuance}我会想起自己从哪里来，也会想起还有哪些事没做完。",
        ),
        (
            "betrayal",
            "{name}面对背叛会怎样反应？",
            "",
            "我最难接受的不是你骗了我。{nuance}是我曾经真的把你放进了计划里，甚至放进了希望里。",
        ),
        (
            "resolve",
            "{name}在最后关头会怎样表态？",
            "局势已经没有完美方案。",
            "那就这样。{nuance}既然没有人能替我承担这个选择，我就自己站到它前面去。",
        ),
    ]
    moods = ["克制", "更锋利", "更疲惫", "更温柔", "更坚定", "更警惕", "更冷静", "更脆弱", "更坦率", "更疏离"]
    focuses = ["自我保护", "关系边界", "过去经历", "当下目标", "世界压力", "信任变化", "行动代价", "隐秘愿望"]
    samples: list[RoleModelDatasetSamplePayload] = []
    for profile in profiles:
        name = profile["name"]
        base = _profile_base_text(profile)[:900]
        related = "；".join(profile.get("related") or []) or "暂无明确关系"
        for index in range(samples_per_character):
            tag, instruction, input_text, output = scene_templates[index % len(scene_templates)]
            mood = moods[(index // len(scene_templates)) % len(moods)]
            focus = focuses[(index // (len(scene_templates) * len(moods))) % len(focuses)]
            nuance = f"这一次，我的语气会更偏向{mood}，重点落在{focus}。"
            rendered_instruction = instruction.format(name=name, world=world_hint, related=related)
            rendered_input = input_text.format(name=name, world=world_hint, related=related)
            rendered_output = output.format(
                name=name,
                base=base,
                world=world_hint,
                related=related,
                nuance=nuance,
            )
            samples.append(
                RoleModelDatasetSamplePayload(
                    id=_sample_id(name, rendered_instruction, rendered_output),
                    character_name=name,
                    instruction=rendered_instruction,
                    input=rendered_input,
                    output=rendered_output,
                    tags=[tag, "supplemental", focus],
                    source_node_ids=[profile["id"]],
                )
            )
    return samples


def generate_dataset(
    project_id: str,
    payload: RoleModelDatasetGenerateRequest | None = None,
) -> RoleModelDatasetPayload:
    """Generate editable SFT samples from current OC character profiles."""
    profiles, context = _character_profiles(project_id)
    samples_per_character, max_samples = _dataset_generation_targets(payload, len(profiles))
    if not profiles:
        samples = _fallback_samples(project_id)
    else:
        ai_samples_per_character = min(samples_per_character, 40)
        system = (
            "你是 OC 角色 LoRA 数据集编写器。根据角色卡生成可微调的小样本。"
            "每条样本必须让助手以角色口吻回答，避免现代 AI 客套话，保持角色设定一致。"
            "输出样本必须可被用户编辑，不要编造与角色卡矛盾的重大事实。"
        )
        user = (
            f"[角色卡]\n{json.dumps(profiles, ensure_ascii=False)}\n\n"
            f"[项目世界/剧情摘要]\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"请为每个角色生成约 {ai_samples_per_character} 条中文或用户原语言的 instruction/input/output 样本。"
            f"总样本数尽量接近但不要超过 {max_samples} 条。"
            "样本需要覆盖自我介绍、关系、冲突、拒绝、安慰、情绪失控、计划、世界观、关键选择、短对白等场景。"
            "id 可以先留空或自拟；source_node_ids 使用角色 id。"
        )
        try:
            out = get_llm_provider().structured(
                [SystemMessage(content=system), HumanMessage(content=user)],
                _DatasetGenerationOutput,
            )
            samples = out.samples if out is not None else []
        except Exception:
            samples = []

        if not samples:
            samples = _fallback_samples(project_id)
        samples.extend(_supplemental_samples(profiles, context, samples_per_character))

    normalized: list[RoleModelDatasetSamplePayload] = []
    seen_ids: set[str] = set()
    for sample in samples:
        if len(normalized) >= max_samples:
            break
        instruction = sample.instruction.strip()
        output = sample.output.strip()
        if not instruction or not output:
            continue
        character_name = sample.character_name.strip() or "角色"
        sample_id = sample.id.strip() or _sample_id(character_name, instruction, output)
        if sample_id in seen_ids:
            continue
        seen_ids.add(sample_id)
        normalized.append(
            RoleModelDatasetSamplePayload(
                id=sample_id,
                character_name=character_name[:80],
                instruction=instruction[:2000],
                input=sample.input[:2000],
                output=output[:4000],
                tags=[tag[:60] for tag in sample.tags[:12]],
                source_node_ids=[str(item) for item in sample.source_node_ids[:12]],
                enabled=sample.enabled,
            )
        )

    dataset = RoleModelDatasetPayload(
        project_id=project_id,
        samples=normalized,
        updated_at=_now(),
    )
    _write_json(_json_path(project_id, "dataset.json"), dataset.model_dump())
    _write_training_jsonl(project_id, dataset)
    return dataset


def get_dataset(project_id: str) -> RoleModelDatasetPayload:
    data = _read_json(_json_path(project_id, "dataset.json"), None)
    if not data:
        return RoleModelDatasetPayload(project_id=project_id, samples=[], updated_at=None)
    return RoleModelDatasetPayload.model_validate(data)


def update_dataset(
    project_id: str,
    payload: RoleModelDatasetUpdateRequest,
) -> RoleModelDatasetPayload:
    samples: list[RoleModelDatasetSamplePayload] = []
    for sample in payload.samples[:1000]:
        if not sample.instruction.strip() or not sample.output.strip():
            continue
        samples.append(
            RoleModelDatasetSamplePayload(
                id=sample.id.strip()[:120] or _sample_id(sample.character_name, sample.instruction, sample.output),
                character_name=sample.character_name.strip()[:80],
                instruction=sample.instruction[:2000],
                input=sample.input[:2000],
                output=sample.output[:4000],
                tags=[tag[:60] for tag in sample.tags[:12]],
                source_node_ids=[str(item) for item in sample.source_node_ids[:12]],
                enabled=sample.enabled,
            )
        )
    dataset = RoleModelDatasetPayload(project_id=project_id, samples=samples, updated_at=_now())
    _write_json(_json_path(project_id, "dataset.json"), dataset.model_dump())
    _write_training_jsonl(project_id, dataset)
    return dataset


def _write_training_jsonl(project_id: str, dataset: RoleModelDatasetPayload) -> None:
    path = _project_dir_checked(project_id) / "train.jsonl"
    lines: list[str] = []
    for sample in dataset.samples:
        if not sample.enabled:
            continue
        system = (
            f"你正在扮演 OC 角色「{sample.character_name or '角色'}」。"
            "回答要贴合角色设定和项目世界观，不要使用“作为AI”这类措辞。"
        )
        user = sample.instruction
        if sample.input.strip():
            user = f"{user}\n\n{sample.input.strip()}"
        lines.append(
            json.dumps(
                {
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": sample.output},
                    ]
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _job_path(project_id: str, kind: str) -> Path:
    return _project_dir_checked(project_id) / f"{kind}_job.json"


def _read_job(project_id: str, kind: str) -> RoleModelJobPayload:
    data = _read_json(_job_path(project_id, kind), None)
    return RoleModelJobPayload.model_validate(data) if data else RoleModelJobPayload()


def _write_job(project_id: str, kind: str, job: RoleModelJobPayload) -> None:
    _write_json(_job_path(project_id, kind), job.model_dump())


def _is_active_job_status(status: str) -> bool:
    return status in {"queued", "running", "starting"}


def _safe_existing_path(path_value: str) -> Path | None:
    if not path_value:
        return None
    try:
        path = Path(path_value)
    except (OSError, ValueError):
        return None
    return path if path.exists() else None


def _model_path_ready(path: Path | None) -> bool:
    if path is None or not path.exists() or path.is_file():
        return False
    has_config = (path / "config.json").exists()
    has_weights = (
        any(path.glob("*.safetensors"))
        or any(path.glob("pytorch_model*.bin"))
        or any(path.glob("model*.bin"))
    )
    return has_config and has_weights


def _default_model_path(project_id: str, model_id: str) -> Path:
    return _project_dir_checked(project_id) / "models" / Path(*model_id.split("/"))


def _default_adapter_path(project_id: str) -> Path:
    return _project_dir_checked(project_id) / "adapter"


def _adapter_path_ready(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    if path.is_file():
        return False
    return (path / "adapter_config.json").exists() or any(path.glob("adapter_model.*"))


def _recover_download_job(project_id: str, job: RoleModelJobPayload) -> RoleModelJobPayload:
    recommendation = get_recommendation(project_id)
    model_id = job.model_id or (recommendation.model_id if recommendation else "")
    path = _safe_existing_path(job.artifact_path)
    if not _model_path_ready(path):
        path = None
    if path is None and model_id:
        fallback = _default_model_path(project_id, model_id)
        path = fallback if _model_path_ready(fallback) else None
    if path is not None and not _is_active_job_status(job.status):
        job.status = "completed"
        job.progress = 1.0
        job.model_id = model_id or job.model_id
        job.artifact_path = str(path.resolve())
        job.message = "模型已下载"
        if not job.finished_at:
            job.finished_at = _now()
        _write_job(project_id, "download", job)
    elif job.status == "completed":
        job.status = "failed"
        job.progress = 1.0
        job.artifact_path = ""
        job.message = "已记录的模型文件不存在，请重新下载当前基础模型。"
        job.finished_at = job.finished_at or _now()
        job.log = [*job.log[-80:], f"{_now()} {job.message}"]
        _write_job(project_id, "download", job)
    return job


def _recover_training_job(project_id: str, job: RoleModelJobPayload) -> RoleModelJobPayload:
    path = _safe_existing_path(job.artifact_path)
    if path is None:
        fallback = _default_adapter_path(project_id)
        path = fallback if _adapter_path_ready(fallback) else None
    if path is not None and _adapter_path_ready(path) and not _is_active_job_status(job.status):
        job.status = "completed"
        job.progress = 1.0
        job.artifact_path = str(path.resolve())
        job.message = "LoRA adapter 已就绪"
        if not job.finished_at:
            job.finished_at = _now()
        _write_job(project_id, "train", job)
    elif job.status == "completed":
        job.status = "failed"
        job.progress = 1.0
        job.artifact_path = ""
        job.message = "已记录的 LoRA adapter 不存在，请重新训练角色模型。"
        job.finished_at = job.finished_at or _now()
        job.log = [*job.log[-80:], f"{_now()} {job.message}"]
        _write_job(project_id, "train", job)
    return job


def _local_runtime_status(
    training: RoleModelJobPayload,
    download: RoleModelJobPayload,
) -> tuple[bool, bool, str]:
    adapter_path = _safe_existing_path(training.artifact_path)
    model_path = _safe_existing_path(download.artifact_path)
    adapter_ready = (
        training.status == "completed"
        and _adapter_path_ready(adapter_path)
        and _model_path_ready(model_path)
    )
    if not adapter_ready:
        return False, False, "本地 LoRA adapter 或基础模型尚未就绪。"
    try:
        import torch  # type: ignore
        import peft  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return True, False, "已找到训练产物，但当前后端缺少 torch/transformers/peft 推理依赖，将使用 API 兜底。"
    if not torch.cuda.is_available():
        return True, False, "已找到训练产物，但当前 PyTorch 未启用 CUDA；为避免 CPU 加载大模型卡死，将使用 API 兜底。"
    return True, True, ""


def _append_job_log(project_id: str, kind: str, message: str, *, status: str | None = None, progress: float | None = None, artifact_path: str | None = None) -> RoleModelJobPayload:
    job = _read_job(project_id, kind)
    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = max(0.0, min(float(progress), 1.0))
    if artifact_path is not None:
        job.artifact_path = artifact_path
    job.message = message
    job.log = [*job.log[-80:], f"{_now()} {message}"]
    if status in {"completed", "failed", "blocked"}:
        job.finished_at = _now()
    _write_job(project_id, kind, job)
    return job


def _thread_key(project_id: str, kind: str) -> tuple[str, str]:
    return (project_id, kind)


def _job_thread_alive(project_id: str, kind: str) -> bool:
    thread = _RUNNING_THREADS.get(_thread_key(project_id, kind))
    return bool(thread and thread.is_alive())


def _read_live_job(project_id: str, kind: str) -> RoleModelJobPayload:
    job = _read_job(project_id, kind)
    if _is_active_job_status(job.status) and not _job_thread_alive(project_id, kind):
        message = "任务已中断：后端服务重启或任务线程不存在，请重新启动任务。"
        job.status = "failed"
        job.message = message
        job.progress = 1.0
        job.finished_at = _now()
        job.log = [*job.log[-80:], f"{_now()} {message}"]
        _write_job(project_id, kind, job)
    return job


def _start_thread(project_id: str, kind: str, target) -> RoleModelJobPayload:
    key = _thread_key(project_id, kind)
    with _THREAD_LOCK:
        existing = _RUNNING_THREADS.get(key)
        if existing and existing.is_alive():
            return _read_job(project_id, kind)
        thread = threading.Thread(target=target, name=f"role-model-{kind}-{project_id}", daemon=True)
        _RUNNING_THREADS[key] = thread
        thread.start()
    return _read_job(project_id, kind)


def start_model_download(project_id: str, payload: RoleModelDownloadRequest) -> RoleModelJobPayload:
    recommendation = get_recommendation(project_id)
    model_id = payload.model_id or (recommendation.model_id if recommendation else _MODEL_CANDIDATES[0]["model_id"])
    model_id = _validate_model_id(model_id)
    existing = get_download_status(project_id)
    if _is_active_job_status(existing.status):
        return existing
    existing_path = _safe_existing_path(existing.artifact_path)
    if (
        existing.status == "completed"
        and existing.model_id == model_id
        and _model_path_ready(existing_path)
    ):
        existing.message = "模型已下载，可直接训练。"
        _write_job(project_id, "download", existing)
        return existing

    job = RoleModelJobPayload(
        status="running",
        message="准备下载模型",
        progress=0.02,
        model_id=model_id,
        started_at=_now(),
        log=[f"{_now()} 准备下载 {model_id}"],
    )
    _write_job(project_id, "download", job)

    def run() -> None:
        try:
            _append_job_log(project_id, "download", "检查 ModelScope SDK", progress=0.08)
            try:
                from modelscope import snapshot_download  # type: ignore
            except Exception:
                try:
                    from modelscope.hub.snapshot_download import snapshot_download  # type: ignore
                except Exception as exc:
                    raise RuntimeError(
                        "未安装 modelscope。请在后端 Python 环境安装 modelscope 后重试；"
                        "也可以在前端打开 ModelScope 链接手动下载。"
                    ) from exc

            models_root = _project_dir_checked(project_id) / "models"
            models_root.mkdir(parents=True, exist_ok=True)
            _append_job_log(project_id, "download", "开始从 ModelScope 下载，耗时取决于网络和模型大小", progress=0.15)
            local_path = snapshot_download(model_id, cache_dir=str(models_root))
            _append_job_log(
                project_id,
                "download",
                "模型下载完成",
                status="completed",
                progress=1.0,
                artifact_path=str(Path(local_path).resolve()),
            )
        except Exception as exc:  # noqa: BLE001
            _append_job_log(project_id, "download", f"模型下载失败：{exc}", status="failed", progress=1.0)

    return _start_thread(project_id, "download", run)


def get_download_status(project_id: str) -> RoleModelJobPayload:
    return _recover_download_job(project_id, _read_live_job(project_id, "download"))


def _training_params(
    request: RoleModelTrainRequest,
    recommendation: RoleModelRecommendationPayload | None,
) -> dict[str, Any]:
    return {
        "epochs": max(0.1, min(float(request.epochs or 1.0), 5.0)),
        "batch_size": max(1, min(int(request.batch_size or recommendation.batch_size if recommendation else request.batch_size or 1), 8)),
        "gradient_accumulation_steps": max(
            1,
            min(
                int(request.gradient_accumulation_steps or recommendation.gradient_accumulation_steps if recommendation else request.gradient_accumulation_steps or 8),
                64,
            ),
        ),
        "lora_rank": max(4, min(int(request.lora_rank or recommendation.lora_rank if recommendation else request.lora_rank or 8), 64)),
        "lora_alpha": max(8, min(int(request.lora_alpha or recommendation.lora_alpha if recommendation else request.lora_alpha or 16), 128)),
        "learning_rate": max(
            0.00001,
            min(float(request.learning_rate or recommendation.learning_rate if recommendation else request.learning_rate or 0.0002), 0.001),
        ),
        "max_seq_length": max(256, min(int(request.max_seq_length or recommendation.max_seq_length if recommendation else request.max_seq_length or 1024), 4096)),
    }


def start_training(project_id: str, request: RoleModelTrainRequest) -> RoleModelJobPayload:
    existing = get_training_status(project_id)
    if _is_active_job_status(existing.status):
        return existing

    recommendation = get_recommendation(project_id)
    model_id = _validate_model_id(request.model_id or (recommendation.model_id if recommendation else _MODEL_CANDIDATES[0]["model_id"]))
    dataset = get_dataset(project_id)
    enabled_count = len([sample for sample in dataset.samples if sample.enabled])
    if enabled_count < _DATASET_MIN_TRAINING_SAMPLES:
        job = RoleModelJobPayload(
            status="blocked",
            message=f"可用训练样本不足 {_DATASET_MIN_TRAINING_SAMPLES} 条，请先生成并确认更多数据。",
            progress=1.0,
            model_id=model_id,
            started_at=_now(),
            finished_at=_now(),
            log=[f"{_now()} 可用训练样本不足：{enabled_count}"],
        )
        _write_job(project_id, "train", job)
        return job

    download = get_download_status(project_id)
    download_path = _safe_existing_path(download.artifact_path)
    if download.status != "completed" or not _model_path_ready(download_path) or download.model_id != model_id:
        job = RoleModelJobPayload(
            status="blocked",
            message="当前模型尚未下载完成，请先下载与训练参数一致的基础模型。",
            progress=1.0,
            model_id=model_id,
            started_at=_now(),
            finished_at=_now(),
            log=[f"{_now()} 模型未就绪：selected={model_id}; downloaded={download.model_id or 'none'}"],
        )
        _write_job(project_id, "train", job)
        return job

    hardware = inspect_hardware(project_id)
    if not hardware.can_train_lora:
        reason = "；".join(hardware.notes or ["未检测到可用 CUDA GPU、足够显存或足够磁盘空间"])
        job = RoleModelJobPayload(
            status="blocked",
            message=f"当前硬件不满足本地 LoRA 训练条件：{reason}",
            progress=1.0,
            model_id=model_id,
            started_at=_now(),
            finished_at=_now(),
            log=[f"{_now()} 硬件检查未通过：{reason}"],
        )
        _write_job(project_id, "train", job)
        return job

    params = _training_params(request, recommendation)
    job = RoleModelJobPayload(
        status="running",
        message="准备 LoRA 训练",
        progress=0.02,
        model_id=model_id,
        started_at=_now(),
        log=[f"{_now()} 准备 LoRA 训练，样本数 {enabled_count}"],
    )
    _write_job(project_id, "train", job)

    def run() -> None:
        try:
            hardware = inspect_hardware(project_id)
            if not hardware.can_train_lora:
                raise RuntimeError("当前硬件不满足本地 LoRA 训练条件：" + "；".join(hardware.notes or ["未检测到足够显存或磁盘空间"]))

            _append_job_log(project_id, "train", "检查训练依赖", progress=0.08)
            try:
                import torch  # type: ignore
                from datasets import Dataset  # type: ignore
                from peft import LoraConfig, get_peft_model  # type: ignore
                from transformers import (  # type: ignore
                    AutoModelForCausalLM,
                    AutoTokenizer,
                    DataCollatorForLanguageModeling,
                    Trainer,
                    TrainingArguments,
                )
            except Exception as exc:
                raise RuntimeError(
                    "缺少训练依赖。请安装 torch、transformers、datasets、peft 后重试。"
                ) from exc

            if not torch.cuda.is_available():
                raise RuntimeError("PyTorch 未检测到 CUDA，已停止训练以避免 CPU 训练卡死。")

            download = get_download_status(project_id)
            model_path = Path(download.artifact_path) if download.artifact_path else None
            if not _model_path_ready(model_path):
                raise RuntimeError("未找到已下载的基础模型，请先完成模型下载。")

            train_jsonl = _project_dir_checked(project_id) / "train.jsonl"
            rows = []
            for line in train_jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            if not rows:
                raise RuntimeError("训练 JSONL 为空。")

            _append_job_log(project_id, "train", "加载 tokenizer 和基础模型", progress=0.16)
            tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                device_map="auto",
                torch_dtype=torch.float16,
            )
            lora_config = LoraConfig(
                r=params["lora_rank"],
                lora_alpha=params["lora_alpha"],
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                lora_dropout=0.05,
                bias="none",
                task_type="CAUSAL_LM",
            )
            model = get_peft_model(model, lora_config)

            def format_messages(item: dict[str, Any]) -> str:
                messages = item.get("messages") or []
                if hasattr(tokenizer, "apply_chat_template"):
                    return tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=False,
                    )
                return "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages)

            dataset_obj = Dataset.from_list([{"text": format_messages(row)} for row in rows])

            def tokenize(batch):
                tokens = tokenizer(
                    batch["text"],
                    max_length=params["max_seq_length"],
                    truncation=True,
                    padding=False,
                )
                tokens["labels"] = list(tokens["input_ids"])
                return tokens

            tokenized = dataset_obj.map(tokenize, remove_columns=["text"])
            output_dir = _project_dir_checked(project_id) / "adapter"
            output_dir.mkdir(parents=True, exist_ok=True)
            _append_job_log(project_id, "train", "开始训练", progress=0.28)
            args = TrainingArguments(
                output_dir=str(output_dir),
                num_train_epochs=params["epochs"],
                per_device_train_batch_size=params["batch_size"],
                gradient_accumulation_steps=params["gradient_accumulation_steps"],
                learning_rate=params["learning_rate"],
                logging_steps=5,
                save_strategy="epoch",
                fp16=True,
                report_to=[],
            )
            trainer = Trainer(
                model=model,
                args=args,
                train_dataset=tokenized,
                data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
            )
            trainer.train()
            model.save_pretrained(str(output_dir))
            tokenizer.save_pretrained(str(output_dir))
            _LOCAL_RUNTIME_CACHE.clear()
            _append_job_log(
                project_id,
                "train",
                "LoRA 训练完成",
                status="completed",
                progress=1.0,
                artifact_path=str(output_dir.resolve()),
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            status = "blocked" if "缺少训练依赖" in message or "硬件" in message or "CUDA" in message else "failed"
            _append_job_log(project_id, "train", f"训练停止：{message}", status=status, progress=1.0)

    return _start_thread(project_id, "train", run)


def get_training_status(project_id: str) -> RoleModelJobPayload:
    return _recover_training_job(project_id, _read_live_job(project_id, "train"))


def get_role_model_state(project_id: str) -> RoleModelStatePayload:
    dataset = get_dataset(project_id)
    hardware_data = _read_json(_json_path(project_id, "hardware.json"), None)
    recommendation = get_recommendation(project_id)
    download = get_download_status(project_id)
    training = get_training_status(project_id)
    adapter_ready, local_runtime_ready, runtime_warning = _local_runtime_status(training, download)
    return RoleModelStatePayload(
        project_id=project_id,
        hardware=RoleModelHardwarePayload.model_validate(hardware_data) if hardware_data else None,
        recommendation=recommendation,
        dataset_count=len(dataset.samples),
        dataset_updated_at=dataset.updated_at,
        download=download,
        training=training,
        adapter_ready=adapter_ready,
        local_runtime_ready=local_runtime_ready,
        runtime_warning=runtime_warning,
        chat_characters=_project_role_names(project_id),
    )


def _context_for_chat(project_id: str, query: str) -> tuple[list[dict[str, Any]], list[str]]:
    with SessionLocal() as db:
        nodes = list(
            db.scalars(
                select(NodeORM)
                .where(NodeORM.project_id == project_id)
                .order_by(NodeORM.sort_order, NodeORM.created_at)
            )
        )
    vector, _, _ = build_project_vector_context(project_id, nodes, query, top_k=5)
    merged = merge_context([], vector)
    return [item.model_dump() for item in merged], [item.id for item in merged]


def _dataset_examples(project_id: str, character_name: str | None) -> str:
    dataset = get_dataset(project_id)
    samples = [
        sample
        for sample in dataset.samples
        if sample.enabled and (not character_name or sample.character_name == character_name)
    ][:5]
    if not samples:
        samples = [sample for sample in dataset.samples if sample.enabled][:5]
    blocks = []
    for sample in samples:
        blocks.append(
            f"用户：{sample.instruction}{chr(10) + sample.input if sample.input else ''}\n角色：{sample.output}"
        )
    return "\n\n".join(blocks)


def _build_role_prompt(
    project_id: str,
    request: RoleModelChatRequest,
    context: list[dict[str, Any]],
) -> str:
    character = _normalize_chat_character(project_id, request.character_name)
    context_block = "\n".join(
        f"- {item.get('title')} ({item.get('type')}): {item.get('content', '')[:500]}"
        for item in context
    ) or "（暂无检索命中）"
    examples = _dataset_examples(project_id, character)
    return (
        f"你正在扮演 OC 角色「{character}」，用户是在和这个角色互动、找灵感。"
        "你不是项目智能体，不负责创建、修改、保存项目设定，也不要用流程化助手口吻。"
        "回答要像角色本人正在说话：自然、具体、有情绪和立场；不要说自己是 AI，不要用客服式套话。"
        "可以参考项目知识库保持设定一致，但不要暴露检索过程。\n\n"
        f"[只读项目设定参考]\n{context_block}\n\n"
        f"[用户已确认的角色说话风格样本]\n{examples or '（暂无样本）'}"
    )


def _history_messages(history: list[RoleModelChatMessagePayload]) -> str:
    clipped = history[-8:]
    return "\n".join(f"{item.role}: {item.content[:800]}" for item in clipped)


def _chat_with_api_fallback(
    project_id: str,
    request: RoleModelChatRequest,
    context: list[dict[str, Any]],
    warning: str,
) -> RoleModelChatResponse:
    system = _build_role_prompt(project_id, request, context)
    history = _history_messages(request.history)
    user = (
        f"[最近对话]\n{history or '（无）'}\n\n"
        f"[用户最新消息]\n{request.message}\n\n"
        "请以角色模型口吻直接回复。"
    )
    try:
        reply = get_llm_provider().chat(
            [SystemMessage(content=system), HumanMessage(content=user)]
        ).strip()
    except Exception as exc:
        reply = f"我现在没法顺利回应，但我已经听见了你的问题：{request.message}"
        warning = f"{warning}；API 兜底也失败：{exc}" if warning else f"API 兜底失败：{exc}"
    context_ids = [str(item.get("id")) for item in context if item.get("id")]
    return RoleModelChatResponse(
        reply=reply,
        mode="api_fallback",
        cited_node_ids=context_ids,
        retrieved_context=context,
        warning=warning,
    )


def _try_local_chat(
    project_id: str,
    request: RoleModelChatRequest,
    context: list[dict[str, Any]],
) -> RoleModelChatResponse | None:
    training = get_training_status(project_id)
    download = get_download_status(project_id)
    _, local_runtime_ready, _ = _local_runtime_status(training, download)
    if not local_runtime_ready:
        return None

    adapter_path = Path(training.artifact_path)
    model_path = Path(download.artifact_path)
    if not _adapter_path_ready(adapter_path) or not _model_path_ready(model_path):
        return None

    cache_key = f"{project_id}:{adapter_path}"
    try:
        runtime = _LOCAL_RUNTIME_CACHE.get(cache_key)
        if runtime is None:
            import torch  # type: ignore
            from peft import PeftModel  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            if not torch.cuda.is_available():
                return None

            tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                device_map="auto" if torch.cuda.is_available() else None,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            model = PeftModel.from_pretrained(model, str(adapter_path))
            model.eval()
            runtime = (tokenizer, model, torch)
            _LOCAL_RUNTIME_CACHE[cache_key] = runtime

        tokenizer, model, torch = runtime
        system = _build_role_prompt(project_id, request, context)
        messages = [{"role": "system", "content": system}]
        for item in request.history[-6:]:
            if item.role in {"user", "assistant"}:
                messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": request.message})
        if hasattr(tokenizer, "apply_chat_template"):
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=True,
                temperature=0.8,
                top_p=0.9,
                repetition_penalty=1.05,
                pad_token_id=tokenizer.eos_token_id,
            )
        decoded = tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        return RoleModelChatResponse(
            reply=decoded or "我需要再想一想。",
            mode="local_lora",
            cited_node_ids=[str(item.get("id")) for item in context if item.get("id")],
            retrieved_context=context,
        )
    except Exception:
        return None


def chat_with_role_model(project_id: str, request: RoleModelChatRequest) -> RoleModelChatResponse:
    with SessionLocal() as db:
        require_project(db, project_id)
    if not request.message.strip():
        raise ValueError("消息不能为空。")
    character = _normalize_chat_character(project_id, request.character_name)
    request = RoleModelChatRequest(
        message=request.message.strip(),
        character_name=character,
        history=request.history,
    )
    request_with_history = _request_with_persisted_history(project_id, request)
    context, _ = _context_for_chat(project_id, f"{character} {request.message}")
    local = _try_local_chat(project_id, request_with_history, context)
    if local is not None:
        _persist_role_model_chat_turn(project_id, request, local)
        return local
    training = get_training_status(project_id)
    download = get_download_status(project_id)
    _, _, runtime_warning = _local_runtime_status(training, download)
    warning = runtime_warning or "本地 LoRA 模型尚未就绪或当前设备缺少推理依赖，已使用主 AI API 按训练样本风格兜底。"
    fallback = _chat_with_api_fallback(project_id, request_with_history, context, warning)
    _persist_role_model_chat_turn(project_id, request, fallback)
    return fallback
