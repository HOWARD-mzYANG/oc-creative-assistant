from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# 服务根目录是 role_finetune_service/。训练工作区、.env 和 README 都相对它定位，
# 不依赖当前启动命令所在目录，方便部署到 AutoDL/Linux 服务器。
SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(SERVICE_ROOT / ".env", override=False)


def _get_bool(name: str, default: bool = False) -> bool:
    """读取布尔环境变量，支持常见写法：1/true/yes/on。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    """读取整数环境变量；格式错误时回退默认值，避免服务启动即崩。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    """读取浮点数环境变量；常用于采样温度这类可调生成参数。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_optional_int(name: str, default: int | None) -> int | None:
    """读取可关闭的整数环境变量。

    例如 `ROLE_QUANTIZATION_BIT=4` 表示 4-bit QLoRA；设为 `0`/`none`/`false`
    则不写入量化配置，改走普通 LoRA。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"", "0", "none", "false", "off"}:
        return None
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class ServiceSettings:
    """训练服务运行配置。

    这里用 dataclass 而不是全局散落的 os.getenv，是为了让训练、聊天和健康检查
    都拿到同一套配置结构。配置每次调用 `get_settings()` 时读取，便于本地调试时
    修改环境变量后重启服务即可生效。
    """

    workspace: Path
    llamafactory_bin: str
    llamafactory_dir: Path | None
    base_model: str
    sample_count: int
    dry_run: bool
    quantization_bit: int | None
    fp16: bool
    bf16: bool
    model_api_auto_start: bool
    model_api_host: str
    model_api_port: int
    model_api_startup_timeout: int
    model_api_base_url: str | None
    model_api_key: str | None
    model_api_name: str
    dataset_api_base_url: str | None
    dataset_api_key: str | None
    dataset_api_model: str
    dataset_api_timeout: int
    dataset_api_batch_size: int
    dataset_api_temperature: float


def get_settings() -> ServiceSettings:
    """从环境变量构造训练服务配置。

    重要变量：
    - ROLE_FINETUNE_WORKSPACE：任务、数据集、日志和 adapter 输出目录。
    - ROLE_TRAINING_DRY_RUN：演示时跳过真实训练，只验证数据和状态链路。
    - ROLE_QUANTIZATION_BIT：QLoRA 量化位数，默认 4；设为 0 可关闭量化。
    - ROLE_TRAINING_FP16 / ROLE_TRAINING_BF16：训练混合精度；普通 AutoDL 卡默认用 fp16。
    - ROLE_MODEL_API_AUTO_START：对话时自动启动/切换 LLaMA-Factory API，默认开启。
    - ROLE_MODEL_API_HOST / ROLE_MODEL_API_PORT：自动启动模型 API 时的监听地址和端口。
    - ROLE_MODEL_API_BASE_URL：可选；自动模式下作为内部访问地址，手动模式下表示外部固定 API。
    - ROLE_DATASET_API_BASE_URL：训练数据生成使用的 OpenAI-style API 地址；配置后 240 条样本必须由 API 生成。
    """
    workspace = Path(
        os.getenv("ROLE_FINETUNE_WORKSPACE", str(SERVICE_ROOT / "workspace"))
    ).expanduser().resolve()
    factory_dir_raw = os.getenv("ROLE_LLAMAFACTORY_DIR")
    factory_dir = Path(factory_dir_raw).expanduser().resolve() if factory_dir_raw else None
    return ServiceSettings(
        workspace=workspace,
        llamafactory_bin=os.getenv("ROLE_LLAMAFACTORY_BIN", "llamafactory-cli"),
        llamafactory_dir=factory_dir,
        base_model=os.getenv("ROLE_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"),
        sample_count=_get_int("ROLE_SAMPLE_COUNT", 240),
        dry_run=_get_bool("ROLE_TRAINING_DRY_RUN", False),
        quantization_bit=_get_optional_int("ROLE_QUANTIZATION_BIT", 4),
        fp16=_get_bool("ROLE_TRAINING_FP16", True),
        bf16=_get_bool("ROLE_TRAINING_BF16", False),
        model_api_auto_start=_get_bool("ROLE_MODEL_API_AUTO_START", True),
        model_api_host=os.getenv("ROLE_MODEL_API_HOST", "127.0.0.1"),
        model_api_port=_get_int("ROLE_MODEL_API_PORT", 8000),
        model_api_startup_timeout=_get_int("ROLE_MODEL_API_STARTUP_TIMEOUT", 180),
        model_api_base_url=os.getenv("ROLE_MODEL_API_BASE_URL") or None,
        model_api_key=os.getenv("ROLE_MODEL_API_KEY") or None,
        model_api_name=os.getenv("ROLE_MODEL_API_NAME", "role-lora"),
        dataset_api_base_url=os.getenv("ROLE_DATASET_API_BASE_URL") or None,
        dataset_api_key=os.getenv("ROLE_DATASET_API_KEY") or None,
        dataset_api_model=os.getenv("ROLE_DATASET_API_MODEL", os.getenv("ROLE_MODEL_API_NAME", "role-data-generator")),
        dataset_api_timeout=_get_int("ROLE_DATASET_API_TIMEOUT", 120),
        dataset_api_batch_size=max(1, min(_get_int("ROLE_DATASET_API_BATCH_SIZE", 20), 40)),
        dataset_api_temperature=_get_float("ROLE_DATASET_API_TEMPERATURE", 0.8),
    )
