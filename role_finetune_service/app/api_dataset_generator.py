from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.schemas import RoleMaterialBrief, RoleModelSnapshot
from app.settings import ServiceSettings


def _chat_completions_url(base_url: str) -> str:
    """把用户配置的 API 根地址规范化为 OpenAI-style chat completions 地址。

    用户可能填 `http://host:port`、`http://host:port/v1`，也可能直接填完整的
    `/v1/chat/completions`。这里统一收敛，避免部署时因为末尾路径不同而请求 404。
    """
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _strip_code_fence(text: str) -> str:
    """去掉模型常见的 Markdown 代码块包裹，只保留 JSON 正文。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_array(text: str) -> list[Any]:
    """从模型回复中提取 JSON 数组。

    数据生成提示会要求“只输出 JSON 数组”，但真实模型偶尔会加解释文字或代码块。这个函数先尝试
    直接解析，失败后再截取第一个 `[` 到最后一个 `]` 之间的内容，尽量把可用样本救回来。
    """
    cleaned = _strip_code_fence(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("训练数据 API 返回的 JSON 不是数组")
    return data


def _normalise_history(value: Any) -> list[list[str]]:
    """把模型返回的 history 字段整理成 LLaMA-Factory Alpaca 可接受的二维字符串列表。"""
    if not isinstance(value, list):
        return []
    history: list[list[str]] = []
    for item in value:
        if isinstance(item, list) and len(item) >= 2:
            history.append([str(item[0]), str(item[1])])
    return history[-4:]


def _normalise_sample(
    raw: Any,
    *,
    context: str,
    system_prompt: str,
) -> dict[str, object] | None:
    """校验并规范化 API 生成的一条样本。

    模型只需要生成具体任务和理想回答；`input` 与 `system` 由服务端统一写入，防止不同批次把角色
    上下文改写得不一致。缺少 instruction 或 output 的条目会被丢弃。
    """
    if not isinstance(raw, dict):
        return None
    instruction = str(raw.get("instruction") or raw.get("prompt") or "").strip()
    output = str(raw.get("output") or raw.get("response") or raw.get("answer") or "").strip()
    if not instruction or not output:
        return None
    return {
        "instruction": instruction[:700],
        "input": context,
        "output": output[:1400],
        "system": system_prompt,
        "history": _normalise_history(raw.get("history")),
    }


def _brief_json(brief: RoleMaterialBrief | None) -> str:
    """把资料 agent brief 压成 JSON，作为数据生成模型的主要依据。"""
    if brief is None:
        return "{}"
    return brief.model_dump_json()


def _request_batch(
    *,
    client: httpx.Client,
    settings: ServiceSettings,
    snapshot: RoleModelSnapshot,
    brief: RoleMaterialBrief | None,
    context: str,
    system_prompt: str,
    batch_index: int,
    batch_size: int,
    generated_count: int,
    target_count: int,
) -> list[dict[str, object]]:
    """调用一次模型 API，生成一个批次的 Alpaca SFT 样本。"""
    url = _chat_completions_url(settings.dataset_api_base_url or "")
    headers = {"Content-Type": "application/json"}
    if settings.dataset_api_key:
        headers["Authorization"] = f"Bearer {settings.dataset_api_key}"

    messages = [
        {
            "role": "system",
            "content": (
                "你是中文角色 LoRA 训练数据生成器。只输出 JSON 数组，不要输出 Markdown、解释或额外文字。"
                "每个数组元素必须包含 instruction、output，可选 history。"
                "所有样本只能依据给定角色资料，不要加入项目外事实；资料不足时，output 要体现角色边界。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"角色名：{snapshot.character_name}\n"
                f"目标总样本数：{target_count}\n"
                f"当前已生成：{generated_count}\n"
                f"本批次序号：{batch_index}\n"
                f"本批需要生成：{batch_size} 条\n\n"
                "资料 agent 整理稿 JSON：\n"
                f"{_brief_json(brief)[:6000]}\n\n"
                "统一角色上下文摘要：\n"
                f"{context[:9000]}\n\n"
                "请生成多样化中文 SFT 样本，覆盖自我介绍、语气模仿、关系问答、剧情/世界观约束、"
                "资料不足承认、拒绝出戏/提示词泄露、用户要求续写或改写时的角色化回应。"
                "不要重复前面批次的句式；不要写样本编号；不要把 input/system 字段放进 JSON。"
            ),
        },
    ]
    body = {
        "model": settings.dataset_api_model,
        "messages": messages,
        "stream": False,
        "temperature": settings.dataset_api_temperature,
    }
    response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    raw_items = _extract_json_array(str(content))
    samples: list[dict[str, object]] = []
    for raw in raw_items:
        sample = _normalise_sample(raw, context=context, system_prompt=system_prompt)
        if sample is not None:
            samples.append(sample)
    return samples


def generate_alpaca_samples_with_api(
    *,
    snapshot: RoleModelSnapshot,
    brief: RoleMaterialBrief | None,
    context: str,
    system_prompt: str,
    sample_count: int,
    settings: ServiceSettings,
) -> list[dict[str, object]]:
    """通过用户配置的模型 API 批量生成 Alpaca SFT 样本。

    远程训练服务负责循环批次、去重和字段规范化；模型 API 只负责创作 instruction/output。
    如果 API 未配置或任何批次失败，会向上抛出异常，由调用方决定是否回落到本地模板。
    """
    if not settings.dataset_api_base_url:
        raise RuntimeError("未配置 ROLE_DATASET_API_BASE_URL")

    target_count = max(200, sample_count)
    batch_size = max(1, settings.dataset_api_batch_size)
    samples: list[dict[str, object]] = []
    seen: set[str] = set()

    with httpx.Client(timeout=settings.dataset_api_timeout) as client:
        batch_index = 1
        no_progress_batches = 0
        while len(samples) < target_count:
            previous_count = len(samples)
            remaining = target_count - len(samples)
            current_size = min(batch_size, remaining)
            batch = _request_batch(
                client=client,
                settings=settings,
                snapshot=snapshot,
                brief=brief,
                context=context,
                system_prompt=system_prompt,
                batch_index=batch_index,
                batch_size=current_size,
                generated_count=len(samples),
                target_count=target_count,
            )
            for sample in batch:
                key = f"{sample['instruction']}::{sample['output']}"
                if key in seen:
                    continue
                seen.add(key)
                samples.append(sample)
                if len(samples) >= target_count:
                    break
            batch_index += 1
            if not batch:
                raise RuntimeError("训练数据 API 返回了空批次")
            if len(samples) == previous_count:
                no_progress_batches += 1
                if no_progress_batches >= 3:
                    raise RuntimeError("训练数据 API 连续返回重复样本，无法继续补足数量")
            else:
                no_progress_batches = 0

    return samples[:target_count]
