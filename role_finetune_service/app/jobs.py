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
from app.schemas import CreateJobRequest, RoleModelJob, RoleModelSnapshot
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


def _log_file(job_id: str, settings: ServiceSettings | None = None) -> Path:
    return _job_dir(job_id, settings) / "train.log"


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
    QLoRA 参数：Qwen2.5-1.5B-Instruct、4-bit、rank 8、alpha 16、3 epochs。
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
        "quantization_bit": 4,
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
        "num_train_epochs": 3.0,
        "lr_scheduler_type": "cosine",
        "warmup_ratio": 0.1,
        "bf16": True,
    }
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
    job = RoleModelJob(
        id=job_id,
        project_id=snapshot.project_id,
        character_id=snapshot.character_id,
        character_name=snapshot.character_name,
        status="queued",
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
        _append_log(job_id, f"[角色微调] 任务 {job_id} 已启动，角色：{snapshot.character_name}")

        # 先把角色快照变成 LLaMA-Factory 可读的数据集。生成失败时不会启动训练，
        # 这样能更快定位是资料问题还是训练环境问题。
        dataset_path, dataset_info_path, actual_count, dataset_name = write_dataset(
            _job_dir(job_id, settings),
            snapshot,
            sample_count,
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
