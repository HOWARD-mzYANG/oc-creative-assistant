from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.dataset import write_dataset
from app.schemas import CreateJobRequest, RoleChatLogItem, RoleMaterialBrief, RoleModelJob, RoleModelSnapshot
from app.settings import ServiceSettings, get_settings


# 训练任务状态用 JSON 文件保存。多个后台线程可能同时更新 job.json，
# 所以用进程内锁保护写入，避免状态文件被交错写坏。
_LOCK = threading.Lock()


def _now() -> datetime:
    """返回带 UTC 时区的当前时间，方便前端和日志稳定排序。"""
    return datetime.now(timezone.utc)


def _jobs_dir(settings: ServiceSettings) -> Path:
    """确保任务根目录存在，并返回 `workspace/jobs`。"""
    path = settings.workspace / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_dir(job_id: str, settings: ServiceSettings | None = None) -> Path:
    """返回单个训练任务目录。

    每个任务目录下会放 `snapshot.json`、`job.json`、`train.log`、`dataset/`
    和 adapter 输出目录，便于迁移、排查和演示。
    """
    settings = settings or get_settings()
    return _jobs_dir(settings) / job_id


def _job_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "job.json"


def _snapshot_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "snapshot.json"


def _material_brief_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "material_brief.json"


def _log_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "train.log"


def _chat_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "chat_history.jsonl"


def _read_log_tail(job_id: str, limit: int = 5000) -> str:
    """读取训练日志尾部，避免接口一次返回完整大日志。"""
    path = _log_file(job_id)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _save_job(job: RoleModelJob) -> None:
    """把任务状态写成 JSON。

    Pydantic 的 `mode="json"` 会把 datetime 转成可序列化字符串，前端可以直接展示。
    """
    path = _job_file(job.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = job.model_dump(mode="json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_job(path: Path) -> RoleModelJob | None:
    """从磁盘读取任务状态；坏文件直接忽略，避免列表接口整体失败。"""
    try:
        return RoleModelJob.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_job(job_id: str) -> RoleModelJob | None:
    """读取单个任务，并动态补上最新日志尾部。"""
    job = _load_job(_job_file(job_id))
    if job is None:
        return None
    return job.model_copy(update={"log_tail": _read_log_tail(job_id)})


def get_material_brief(job_id: str) -> RoleMaterialBrief | None:
    """读取训练任务保存的资料整理稿。"""
    path = _material_brief_file(job_id)
    if not path.exists():
        return None
    try:
        return RoleMaterialBrief.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def append_chat_turn(job_id: str, user_message: str, assistant_message: str) -> None:
    """把一次用户-角色对话追加到远程聊天记录。

    记录保存在 job 目录里，跟 adapter 和训练数据放在一起。这样用户下次选择同一个
    已训练角色模型时，可以继续查看这套模型对应的历史对话。
    """
    path = _chat_file(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now().isoformat()
    rows = [
        {"role": "user", "content": user_message, "created_at": now},
        {"role": "assistant", "content": assistant_message, "created_at": now},
    ]
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_chat_history(job_id: str, limit: int = 80) -> list[RoleChatLogItem]:
    """读取远程聊天记录，默认返回最后若干条。"""
    path = _chat_file(job_id)
    if not path.exists():
        return []
    items: list[RoleChatLogItem] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            items.append(RoleChatLogItem.model_validate_json(line))
        except Exception:
            continue
    return items[-limit:]


def list_jobs(
    *,
    project_id: str | None = None,
    character_id: str | None = None,
    limit: int = 20,
) -> list[RoleModelJob]:
    """列出任务，支持按项目和角色过滤。

    主 app 的角色模型页只需要当前角色最近的训练任务，所以这里按创建时间倒序返回。
    """
    settings = get_settings()
    jobs: list[RoleModelJob] = []
    for path in _jobs_dir(settings).glob("*/job.json"):
        job = _load_job(path)
        if job is None:
            continue
        if project_id and job.project_id != project_id:
            continue
        if character_id and job.character_id != character_id:
            continue
        jobs.append(job.model_copy(update={"log_tail": _read_log_tail(job.id)}))
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    return jobs[:limit]


def _append_log(job_id: str, text: str) -> None:
    """追加一行训练日志。

    训练命令的 stdout/stderr 也会写入同一个文件，前端通过 `log_tail` 展示最新进展。
    """
    path = _log_file(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def _update_job(job_id: str, **patch: Any) -> RoleModelJob:
    """原子更新任务状态文件。

    任务线程会频繁更新状态、样本数、输出路径和错误信息。这里统一加更新时间，
    并用锁保证读取旧状态和写入新状态之间不会被别的线程打断。
    """
    with _LOCK:
        current = get_job(job_id)
        if current is None:
            raise FileNotFoundError(job_id)
        next_job = current.model_copy(update={**patch, "updated_at": _now()})
        _save_job(next_job)
        return next_job


def _write_train_config(
    *,
    job_id: str,
    dataset_name: str,
    dataset_dir: Path,
    adapter_dir: Path,
    settings: ServiceSettings,
) -> Path:
    """生成 LLaMA-Factory 训练 YAML。

    YAML 的字段名是 LLaMA-Factory CLI 约定，必须保持英文。这里固定演示版的
    默认参数：Qwen2.5-1.5B-Instruct、4-bit QLoRA、rank 8、alpha 16、3 epochs。
    如果 `ROLE_QUANTIZATION_BIT=0`，则不写量化配置，改用普通 LoRA。
    混合精度从环境变量读取，默认 fp16，避免普通显卡或 CUDA 环境不支持 bf16 时失败。
    之后如果要做多模型/多显存档位，可以从这里扩展配置模板。
    """
    config = {
        "model_name_or_path": settings.base_model,
        "trust_remote_code": True,
        "stage": "sft",
        "do_train": True,
        "finetuning_type": "lora",
        "lora_rank": 8,
        "lora_alpha": 16,
        "lora_target": "all",
        "dataset": dataset_name,
        "dataset_dir": str(dataset_dir),
        "template": "qwen",
        "cutoff_len": 2048,
        "max_samples": 100000,
        "overwrite_cache": True,
        "preprocessing_num_workers": 4,
        "output_dir": str(adapter_dir),
        "logging_steps": 5,
        "save_steps": 100,
        "plot_loss": True,
        "overwrite_output_dir": True,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "learning_rate": 2.0e-4,
        "num_train_epochs": 10.0,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.1,
        "fp16": settings.fp16,
        "bf16": settings.bf16,
    }
    if settings.quantization_bit:
        config["quantization_bit"] = settings.quantization_bit
    path = _job_dir(job_id, settings) / "train.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def create_job(payload: CreateJobRequest) -> RoleModelJob:
    """创建任务并启动后台训练线程。

    HTTP 请求不能一直阻塞到训练结束，所以接口先写入 queued 状态并立即返回 job。
    后台线程负责生成数据、写配置、调用 LLaMA-Factory，再持续更新状态和日志。
    """
    settings = get_settings()
    settings.workspace.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    job_dir = _job_dir(job_id, settings)
    job_dir.mkdir(parents=True, exist_ok=True)
    snapshot = payload.snapshot
    _snapshot_file(job_id, settings).write_text(
        snapshot.model_dump_json(indent=2),
        encoding="utf-8",
    )
    material_brief_path = ""
    if payload.material_brief is not None:
        material_brief_path = str(_material_brief_file(job_id, settings))
        _material_brief_file(job_id, settings).write_text(
            payload.material_brief.model_dump_json(indent=2),
            encoding="utf-8",
        )
    job = RoleModelJob(
        id=job_id,
        project_id=snapshot.project_id,
        character_id=snapshot.character_id,
        character_name=snapshot.character_name,
        status="queued",
        material_brief_path=material_brief_path,
        created_at=_now(),
        updated_at=_now(),
    )
    _save_job(job)
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, payload.sample_count or settings.sample_count),
        daemon=True,
    )
    thread.start()
    return job


def _run_job(job_id: str, sample_count: int) -> None:
    """后台执行完整训练流程。

    状态流转为 queued -> running -> succeeded/failed。任何异常都会写入日志并标记
    failed，前端轮询接口即可看到失败原因。
    """
    settings = get_settings()
    started = time.time()
    try:
        _update_job(job_id, status="running")
        snapshot = RoleModelSnapshot.model_validate_json(
            _snapshot_file(job_id, settings).read_text(encoding="utf-8")
        )
        material_brief = get_material_brief(job_id)
        _append_log(job_id, f"[角色微调] 任务 {job_id} 已启动，角色：{snapshot.character_name}")

        # 先把角色快照和资料整理稿变成 LLaMA-Factory 可读的数据集。生成失败时不会启动训练，
        # 这样能更快定位是资料问题还是训练环境问题。
        dataset_path, dataset_info_path, actual_count, dataset_name = write_dataset(
            _job_dir(job_id, settings),
            snapshot,
            sample_count,
            material_brief,
        )
        adapter_dir = _job_dir(job_id, settings) / "adapter"

        # 训练配置和数据集路径写回 job.json，前端可以直接展示，也方便演示时打开检查。
        train_config = _write_train_config(
            job_id=job_id,
            dataset_name=dataset_name,
            dataset_dir=dataset_path.parent,
            adapter_dir=adapter_dir,
            settings=settings,
        )
        _update_job(
            job_id,
            sample_count=actual_count,
            dataset_path=str(dataset_path),
            dataset_info_path=str(dataset_info_path),
            train_config_path=str(train_config),
            adapter_path=str(adapter_dir),
        )
        if settings.dry_run:
            _append_log(job_id, "[角色微调] ROLE_TRAINING_DRY_RUN=true，跳过 llamafactory-cli train。")
            time.sleep(0.4)
            _update_job(job_id, status="succeeded")
            _append_log(job_id, f"[角色微调] 干跑任务完成，用时 {time.time() - started:.1f}s")
            return

        command = [settings.llamafactory_bin, "train", str(train_config)]
        _append_log(job_id, "[角色微调] 执行训练命令：" + " ".join(command))
        with _log_file(job_id, settings).open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=str(settings.llamafactory_dir or _job_dir(job_id, settings)),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            code = process.wait()
        if code != 0:
            raise RuntimeError(f"LLaMA-Factory 训练进程退出码为 {code}")
        _update_job(job_id, status="succeeded")
        _append_log(job_id, f"[角色微调] 训练完成，用时 {time.time() - started:.1f}s")
    except Exception as exc:  # noqa: BLE001
        _append_log(job_id, f"[角色微调] 任务失败：{exc}")
        try:
            _update_job(job_id, status="failed", error=str(exc))
        except Exception:
            pass
