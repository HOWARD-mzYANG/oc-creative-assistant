"""LLM 调用的策略模式入口。

将 LangChain / OpenAI SDK 细节封装在 Provider 内部，让 agent 节点只看到 ``chat``
（字符串）和 ``structured``（Pydantic）等统一方法，从而屏蔽底层协议差异。

DeepSeek / 通义等 OpenAI 兼容服务对 ``function_calling`` / ``json_mode`` / thinking
模式的支持差异较大，因此真实 provider 支持按配置选择结构化输出策略，并在协议不兼容时
降级到普通 JSON prompt。Mock provider 完全离线，并按 schema 名返回已注册样例，便于
离线开发和 CI。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.settings import LlmSettings


logger = logging.getLogger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)

_VALID_STRUCTURED_METHODS = frozenset({"function_calling", "json_mode", "plain_json"})
_REASONING_CHUNK_KEYS = (
    "reasoning_content",
    "reasoning",
    "reasoning_text",
    "thinking",
    "thinking_content",
)


@dataclass(frozen=True)
class ChatStreamDelta:
    """流式 LLM 增量：text 是可见回复，reasoning 是 provider 返回的可选 thinking。"""

    text: str = ""
    reasoning: str = ""


def _is_tool_choice_unsupported_error(exc: BaseException) -> bool:
    """判断异常是否来自 thinking 模型不支持 tool_choice 的协议限制。"""
    text = str(exc).lower()
    return "tool_choice" in text and (
        "does not support" in text
        or "unsupported" in text
        or "not support" in text
    )


def _strip_json_fence(text: str) -> str:
    """去掉模型可能包在 JSON 外层的 markdown 代码块。"""
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
    """把结构化调用返回的原始消息压成短片段，供 warning 日志诊断。"""
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


def _content_to_text(content: Any) -> str:
    """将 LangChain/OpenAI 的 content 结构转换成普通可见文本。

    多模态或 OpenAI 兼容扩展有时会把 content 表示成 block 列表；这里只保留
    普通文本块，跳过 reasoning/thinking 块，避免把模型思考混入最终回复。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = str(block.get("type") or "")
                if "reason" in block_type or "thinking" in block_type:
                    continue
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _message_role(message: BaseMessage) -> str:
    """把 LangChain 消息类型映射成 OpenAI SDK 所需的 role 字符串。"""
    message_type = getattr(message, "type", "")
    if message_type == "human":
        return "user"
    if message_type == "ai":
        return "assistant"
    if message_type == "tool":
        return "tool"
    return "system"


def _messages_to_openai(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """将 LangChain 消息列表转换成 OpenAI SDK 原始 chat.completions payload。"""
    payload: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {
            "role": _message_role(message),
            "content": _content_to_text(message.content),
        }
        if isinstance(message, ToolMessage):
            item["tool_call_id"] = message.tool_call_id
        payload.append(item)
    return payload


def _delta_field(delta: Any, key: str) -> Any:
    """兼容 dict / Pydantic 对象 / model_extra 三种 delta 字段读取方式。"""
    if isinstance(delta, dict):
        return delta.get(key)
    value = getattr(delta, key, None)
    if value is not None:
        return value
    model_extra = getattr(delta, "model_extra", None)
    if isinstance(model_extra, dict):
        return model_extra.get(key)
    return None


def _extract_reasoning_text(value: Any, *, known_reasoning_field: bool = False) -> str:
    """从 provider 扩展字段或 reasoning block 中提取 thinking 文本。

    普通字符串只有在已知来源就是 reasoning 字段时才会被采纳，防止把常规回复
    content 误判成“模型原始思考”。
    """
    if isinstance(value, str):
        return value if known_reasoning_field else ""
    if isinstance(value, dict):
        parts: list[str] = []
        for key in _REASONING_CHUNK_KEYS:
            item = value.get(key)
            if isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")
                if "reason" in item_type or "thinking" in item_type:
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    parts.append(_extract_reasoning_text(item))
            elif isinstance(item, str) and known_reasoning_field:
                parts.append(item)
        return "".join(parts)
    return ""


def _reasoning_from_chunk(chunk: Any) -> str:
    """从 LangChain/OpenAI 兼容消息块中收集 reasoning_content 等扩展字段。"""
    parts: list[str] = []
    for attr_name in ("additional_kwargs", "response_metadata"):
        data = getattr(chunk, attr_name, None)
        if not isinstance(data, dict):
            continue
        for key in _REASONING_CHUNK_KEYS:
            value = data.get(key)
            text = _extract_reasoning_text(value, known_reasoning_field=True)
            if text:
                parts.append(text)
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        content_text = _extract_reasoning_text(content)
        if content_text:
            parts.append(content_text)
    return "".join(parts)


def extract_provider_reasoning(message: Any) -> str:
    """提取 OpenAI 兼容响应中显式返回的 provider thinking。"""
    return _reasoning_from_chunk(message)


class LlmProvider(Protocol):
    """LLM 调用的统一接口契约。

    每个 agent 节点都通过该协议的实现访问模型；策略模式允许 mock 与真实 provider 通过
    .env 无缝切换，无需修改业务代码。
    """

    def chat(self, messages: list[BaseMessage]) -> str: ...

    def chat_stream(self, messages: list[BaseMessage]) -> Iterator[str]: ...

    def chat_stream_chunks(self, messages: list[BaseMessage]) -> Iterator[ChatStreamDelta]: ...

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

        methods = tuple(
            method
            for method in settings.structured_methods
            if method in _VALID_STRUCTURED_METHODS
        )
        self._structured_methods = methods or ("function_calling", "json_mode", "plain_json")
        self._disabled_structured_methods: set[str] = set()
        self._stream_reasoning = settings.stream_reasoning
        self._base_url = settings.base_url
        self._api_key = settings.api_key
        self._model = settings.model
        self._openai_client: Any | None = None

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

    def chat_stream_chunks(self, messages: list[BaseMessage]) -> Iterator[ChatStreamDelta]:
        """逐块产出文本/思考增量；LangChain ChatOpenAI 的 .stream() 原生支持。

        DeepSeek 等模型可能把 thinking 放在 chunk.additional_kwargs.reasoning_content；
        只有开启 OC_LLM_STREAM_REASONING 时才向上游暴露这部分内容。
        """
        if self._stream_reasoning:
            yield from self._chat_stream_chunks_openai_sdk(messages)
            return

        for chunk in self._client.stream(messages):
            content = getattr(chunk, "content", chunk)
            text = _content_to_text(content)
            reasoning = _reasoning_from_chunk(chunk) if self._stream_reasoning else ""
            if text or reasoning:
                yield ChatStreamDelta(text=text, reasoning=reasoning)

    def _chat_stream_chunks_openai_sdk(
        self,
        messages: list[BaseMessage],
    ) -> Iterator[ChatStreamDelta]:
        """使用 OpenAI SDK 原始流读取 content / reasoning_content。

        LangChain 对 OpenAI 兼容扩展字段的透传取决于版本；这里在开启原始 thinking 展示时
        直接读取 delta.reasoning_content，使 DeepSeek 的思考流更可靠地到达前端。
        """
        stream = self._get_openai_client().chat.completions.create(
            model=self._model,
            messages=_messages_to_openai(messages),
            temperature=0.3,
            stream=True,
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            text = _delta_field(delta, "content") or ""
            reasoning = _delta_field(delta, "reasoning_content") or ""
            if text or reasoning:
                yield ChatStreamDelta(text=str(text), reasoning=str(reasoning))

    def _get_openai_client(self) -> Any:
        if self._openai_client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError("未安装 openai 依赖，无法读取原始 reasoning_content 流") from error
            self._openai_client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._openai_client

    def chat_stream(self, messages: list[BaseMessage]) -> Iterator[str]:
        """逐块产出可见回复文本增量。"""
        for chunk in self.chat_stream_chunks(messages):
            if chunk.text:
                yield chunk.text

    def structured(
        self,
        messages: list[BaseMessage],
        schema: type[TSchema],
    ) -> TSchema:
        """结构化输出；为返回空解析结果的 OpenAI 兼容 provider 提供兜底。"""
        errors: list[str] = []

        for method in self._structured_methods:
            if method in self._disabled_structured_methods:
                continue
            try:
                if method == "plain_json":
                    return self._structured_via_plain_json(messages, schema)
                parsed, err = self._try_structured(messages, schema, method)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{method}: {exc}")
                if method == "function_calling" and _is_tool_choice_unsupported_error(exc):
                    self._disabled_structured_methods.add(method)
                    logger.warning(
                        "%s structured via %s is unsupported by this model; "
                        "will skip it for the rest of this process. "
                        "For thinking models, set OC_LLM_STRUCTURED_METHOD=plain_json.",
                        schema.__name__,
                        method,
                    )
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

        detail = "; ".join(errors) if errors else "no structured methods were available"
        raise ValueError(f"structured output failed for {schema.__name__}: {detail}")

    def _messages_for_json_mode(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """确保 json_mode 请求满足 OpenAI 兼容服务的 JSON 关键词要求。"""
        return [
            *messages,
            HumanMessage("请只输出一个 JSON 对象，不要 markdown 代码块，不要说明文字。"),
        ]

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
        invoke_messages = self._messages_for_json_mode(messages) if method == "json_mode" else messages
        result = runnable.invoke(invoke_messages)

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
        try:
            bound = self._client.bind_tools(tools)
            response = bound.invoke(messages)
        except Exception as exc:  # noqa: BLE001
            if not _is_tool_choice_unsupported_error(exc):
                raise
            logger.warning(
                "Tool calling is unsupported by this model; falling back to plain chat. "
                "For thinking models, this skips active tool use in the current turn: %s",
                exc,
            )
            return AIMessage(content=self.chat(messages))
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

    def chat_stream_chunks(self, messages: list[BaseMessage]) -> Iterator[ChatStreamDelta]:
        """Mock 模式只模拟可见文本，不模拟 provider thinking。"""
        for token in self.chat_stream(messages):
            yield ChatStreamDelta(text=token)

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
