"""LLM 调用的策略模式入口。

将 LangChain / OpenAI SDK 细节封装在 Provider 内部，让 agent 节点只看到 ``chat``
（字符串）和 ``structured``（Pydantic）等统一方法，从而屏蔽底层协议差异。

DeepSeek / 通义等 OpenAI 兼容服务通常不支持 ``response_format=json_schema``，
因此真实 provider 会显式固定 ``method="function_calling"``，用 tool-calls 协议获得
更广兼容。Mock provider 完全离线，并按 schema 名返回已注册样例，便于离线开发和 CI。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any, Protocol, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.settings import LlmSettings


logger = logging.getLogger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)

_STRUCTURED_METHODS = ("function_calling", "json_mode")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    """从纯文本模型回复中提取 JSON 对象。"""
    cleaned = _strip_json_fence(text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match is None:
        raise ValueError("模型回复中未找到 JSON 对象")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("模型 JSON 根节点必须是对象")
    return data


def _raw_message_snippet(raw: Any, *, limit: int = 240) -> str:
    if raw is None:
        return ""
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        content = "\n".join(parts)
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


class LlmProvider(Protocol):
    """LLM 调用的统一接口契约。

    每个 agent 节点都通过该协议的实现访问模型；策略模式允许 mock 与真实 provider 通过
    .env 无缝切换，无需修改业务代码。
    """

    def chat(self, messages: list[BaseMessage]) -> str: ...

    def chat_stream(self, messages: list[BaseMessage]) -> Iterator[str]: ...

    def structured(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
    ) -> TSchema: ...

    def chat_with_tools(
        self,
        messages: list[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage: ...


class OpenAICompatibleProvider:
    """通过 OpenAI 兼容协议调用 DeepSeek / 通义 / 官方 OpenAI 等服务。

    底层使用 LangChain 的 ``ChatOpenAI``，后续接入 ToolNode / Checkpointer 时可以直接
    复用 LangChain 生态，而不用手写 tool-calling 循环。
    """

    def __init__(self, settings: LlmSettings) -> None:
        if not settings.is_configured:
            raise ValueError("缺少 OC_LLM_* 配置，无法初始化 OpenAI 兼容 provider")

        self._client = ChatOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            temperature=0.3,
        )

    def chat(self, messages: list[BaseMessage]) -> str:
        response = self._client.invoke(messages)
        content = response.content if isinstance(response, AIMessage) else response
        return content if isinstance(content, str) else str(content)

    def chat_stream(self, messages: list[BaseMessage]) -> Iterator[str]:
        """逐块产出文本增量；LangChain ChatOpenAI 的 .stream() 原生支持。

        空 chunk（例如 LLM 仍在思考、尚未产出 token）会被跳过，因此上层只会看到有真实内容的
        token，避免把 None / "" 放进字符串累积。
        """
        for chunk in self._client.stream(messages):
            content = chunk.content if isinstance(chunk, AIMessage) else chunk
            if isinstance(content, str) and content:
                yield content

    def structured(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
    ) -> TSchema:
        """结构化输出；为返回空解析结果的 OpenAI 兼容 provider 提供兜底。"""
        errors: list[str] = []

        for method in _STRUCTURED_METHODS:
            try:
                parsed, err = self._try_structured(messages, schema, method)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{method}: {exc}")
                logger.warning(
                    "%s structured via %s raised: %s",
                    schema.__name__,
                    method,
                    exc,
                )
                continue

            if parsed is not None:
                return parsed
            if err:
                errors.append(err)

        try:
            return self._structured_via_plain_json(messages, schema)
        except Exception as exc:  # noqa: BLE001
            detail = "; ".join(errors) if errors else str(exc)
            raise ValueError(
                f"structured output failed for {schema.__name__}: {detail}"
            ) from exc

    def _try_structured(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
        method: str,
    ) -> tuple[TSchema | None, str | None]:
        runnable = self._client.with_structured_output(
            schema,
            method=method,
            include_raw=True,
        )
        result = runnable.invoke(messages)

        if not isinstance(result, dict):
            if result is None:
                return None, f"{method}: parsed is None"
            return result, None

        parsed = result.get("parsed")
        if parsed is not None:
            return parsed, None

        parsing_error = result.get("parsing_error")
        raw_snippet = _raw_message_snippet(result.get("raw"))
        err_parts = [f"{method}: parsed is None"]
        if parsing_error is not None:
            err_parts.append(f"parsing_error={parsing_error}")
        if raw_snippet:
            err_parts.append(f"raw={raw_snippet}")
        err = "; ".join(err_parts)
        logger.warning("%s structured call returned None (%s)", schema.__name__, err)
        return None, err

    def _structured_via_plain_json(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
    ) -> TSchema:
        """最后兜底：普通 chat + 手动 JSON 解析（适用于 tool-calls 被忽略的情况）。"""
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        prompt_messages = [
            *messages,
            HumanMessage(
                "只回复一个符合该 schema 的 JSON 对象"
                "（不要 markdown 代码块，不要说明文字）：\n"
                f"{schema_json}"
            ),
        ]
        raw = self.chat(prompt_messages)
        data = _extract_json_object(raw)
        return schema.model_validate(data)

    def chat_with_tools(
        self,
        messages: list[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        """绑定工具并调用一次 LLM，返回原始 AIMessage 供 tool_loop 解析 tool_calls。"""
        bound = self._client.bind_tools(tools)
        response = bound.invoke(messages)
        if isinstance(response, AIMessage):
            return response
        return AIMessage(content=str(getattr(response, "content", response)))

_MOCK_SAMPLES: dict[str, dict[str, Any]] = {
    "IntentClassification": {
        "primary": "inspiration",
        "confidence": 0.85,
        "reasoning": "The user wants to explore creative directions, matching the inspiration intent.",
    },
    "InspirationOutput": {
        "reasoning": "Add background conflict around the existing dwarven-blacksmith setting to make the character more three-dimensional.",
        "suggestions": [
            "Design a past for the blacksmith in which she was exiled by the clan chief",
            "Introduce a young apprentice who challenges her craft",
            "Have her hold an artifact that reveals an ancestral secret",
        ],
        "referenced_node_ids": [],
        "proposed_changes": [
            {
                "change_type": "create_node",
                "target_id": None,
                "pending_id": "pending-1",
                "payload": {
                    "title": "Duskstone",
                    "content": "A young dwarven apprentice, studying under the protagonist, secretly suspicious of her master's past",
                    "node_type": "character",
                },
                "reason": "Introduce a conflict line for the protagonist",
            }
        ],
    },
    "ResearchOutput": {
        "reasoning": "Summarize related characters and worldbuilding fragments by theme within the existing graph.",
        "summary": "[mock] This character has historical entanglements with the existing clan; the core conflict stems from identity.",
        "referenced_node_ids": [],
        "proposed_changes": [],
    },
    "StructureOutput": {
        "reasoning": "The character the user selected isn't yet connected to the plot; add an interaction line.",
        "summary": "Recommend adding an opposing interaction line between the character and the clan chief.",
        "proposed_changes": [],
    },
    "SimulationOutput": {
        "reasoning": "Lay out multiple directions for the user's hypothesis and assess the impact on existing nodes.",
        "branches": [
            {
                "scenario": "She accepts the mission but leaves herself a way out",
                "likelihood": "high",
                "downstream_impacts": ["The clan reconciles for now", "The apprentice's identity becomes a mystery"],
                "affected_node_ids": [],
            }
        ],
    },
    "ChatAssemblerOutput": {
        "reply_text": "[mock] For the blacksmith's story, here are a few directions: an exiled past, a young apprentice, an ancestral artifact.",
        "cited_node_ids": [],
        "staging_summary": "I'm ready to add 1 item for you, pending your confirmation.",
    },
    "ChatMetadataOutput": {
        "cited_node_ids": [],
        "staging_summary": "I'm ready to add 1 item for you, pending your confirmation.",
    },
        "SummaryOutput": {
        "summary": "[mock] The user and the agent had several rounds of discussion about the protagonist's past and the clan conflict, reaching basic consensus on the main direction.",
        "key_facts": [
            "The protagonist is a dwarven blacksmith with a questionable origin",
            "The user leans toward having the conflict come from within the clan",
        ],
    },
    "StructuredExtractionOutput": {
        "reasoning": "[mock] Extracted one character and one worldbuilding setting from the conversation.",
        "entities": [
            {"type": "character", "name": "Duskstone", "attributes": {"role": "dwarven blacksmith"}},
            {"type": "world", "name": "Ironforge Clan", "attributes": {}},
        ],
        "relations": [
            {"source_name": "Duskstone", "target_name": "Ironforge Clan", "label": "belongs to"},
        ],
        "deferred_fields": [{"entity": "Duskstone", "field": "appearance"}],
    },
    "QuestionPlannerOutput": {
        "reasoning": "[mock] The character has an identity but lacks motivation; ask about motivation.",
        "next_question": "Why did Duskstone leave the Ironforge Clan?",
        "target_field": "motivation",
    },
    "SeedOutput": {
        "worldview_summary": "[mock] A fantasy world centered on a clan of dwarven blacksmiths.",
        "main_characters": ["Duskstone"],
        "plot_outline": "[mock] The protagonist comes into conflict with the clan over the mystery of her origin.",
        "style_notes": "A weighty, introspective low-fantasy tone.",
    },
    "WorkspaceInspirationOutput": {
        "reasoning": "[mock] The user is sharing an idea; give positive feedback.",
        "type": "feedback",
        "content": "[mock] This direction is really interesting — especially with the conflict coming from within, the tension will be strong.",
    },
}


class MockProvider:
    """离线、确定性的桩实现，不发起网络请求。

    根据目标 schema 名返回 ``_MOCK_SAMPLES`` 中注册的样例，让前端集成和单元测试在没有 LLM
    时也能运行。未注册 schema 会抛错，因为暴露遗漏比静默返回 None 更安全。
    """

    def chat(self, messages: list[BaseMessage]) -> str:
        last_user = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        text = last_user if isinstance(last_user, str) else str(last_user)
        return f"[mock] received: {text[:60]}"

    def chat_stream(self, messages: list[BaseMessage]) -> Iterator[str]:
        """按字符拆分来模拟 token 流，使 mock 模式也能验证前端渐进渲染。"""
        for ch in self.chat(messages):
            yield ch

    def structured(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
    ) -> TSchema:
        sample = _MOCK_SAMPLES.get(schema.__name__)
        if sample is None:
            raise ValueError(
                f"MockProvider 缺少 {schema.__name__} 样例；请在 _MOCK_SAMPLES 中注册"
            )
        return schema.model_validate(sample)

    def chat_with_tools(
        self,
        messages: list[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        """Mock 模式跳过工具调用并返回空回复，让 tool_loop 立即退出。"""
        return AIMessage(content="")
