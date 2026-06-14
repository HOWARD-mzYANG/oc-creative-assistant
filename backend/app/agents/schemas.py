"""Agent 编排中使用的 Pydantic 数据契约。

集中在这里后，每个 LangGraph 节点只需要依赖单一入口
``app.agents.schemas``；如果后续 LLM 输出协议需要从
function_calling 切回 json_schema，也只需改动一处。

每个 agent 输出都要求携带 ``reasoning`` 字段：它既是显式 CoT 的落点，
也方便用户在 UI 中看到“为什么提出这个建议”，并与 staging 表中的
``reason`` 字段相呼应。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class _LlmStructuredOutput(BaseModel):
    """所有 agent 输出 schema 的基类。

    OpenAI 兼容服务（尤其是 DeepSeek）的 function_calling 协议偶尔会把
    list / dict 字段二次序列化成 JSON 字符串，再塞进 tool call 参数里，
    导致 Pydantic 抛出类似 ``list_type`` 的校验错误。这里在
    ``mode='before'`` 阶段对顶层 dict 字段做轻量解析：看起来像 JSON
    数组或对象的字符串会传给 ``json.loads``；解析失败则保持原样，交给
    后续校验分类。
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_stringified_json(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        for key, value in list(data.items()):
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            looks_like_json = (
                (stripped.startswith("[") and stripped.endswith("]"))
                or (stripped.startswith("{") and stripped.endswith("}"))
            )
            if not looks_like_json:
                continue
            try:
                data[key] = json.loads(stripped)
            except json.JSONDecodeError:
                pass

        return data


IntentLiteral = Literal[
    "inspiration",
    "research",
    "structure",
    "simulation",
    "small_talk",
]
"""主意图取值；small_talk 是所有未落入四个 agent 的闲聊兜底。"""

ChangeTypeLiteral = Literal[
    "create_node",
    "create_edge",
    "update_node",
    "delete_node",
    "delete_edge",
]
"""staging 表支持的画布变更类型；删除也会经过 staging 用户确认。
   HITL 保证内容不会绕过用户直接删除，因此可以与 create / update
   共用同一条通道。"""


class IntentClassification(_LlmStructuredOutput):
    """intent_router 的结构化输出，用于把用户消息分类到某个 agent 类型。

    primary 决定图会路由到哪个 agent 节点，也作为 assembler 选择回复主线
    （语气、副作用归属）的依据。confidence 保留给前端调试和未来阈值控制，
    当前不参与路由决策。
    """

    primary: IntentLiteral
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    reasoning: str = ""


class ProposedChange(_LlmStructuredOutput):
    """agent 想要执行的画布变更，会进入 staging 表等待用户确认。

    ``pending_id`` 会为同一批次中的新节点分配临时占位 ID，使边可以引用尚未
    持久化的新节点；真正的 node_id 会在提交时回填，从而解决“先节点后边”
    的依赖问题。
    """

    change_type: ChangeTypeLiteral
    target_id: str | None = None
    pending_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class WebSourceItem(BaseModel):
    """以链接卡形式展示给前端的网页搜索命中。"""

    title: str = ""
    url: str
    snippet: str = ""


class InspirationOutput(_LlmStructuredOutput):
    """灵感 agent 输出，侧重开放式建议，不强制写入画布。"""

    reasoning: str
    suggestions: list[str] = Field(default_factory=list)
    referenced_node_ids: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)


class ResearchOutput(_LlmStructuredOutput):
    """研究 / 检索 agent 输出，必须携带引用，默认不写入画布。"""

    reasoning: str
    summary: str
    referenced_node_ids: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    web_sources: list[WebSourceItem] = Field(default_factory=list)


class StructureOutput(_LlmStructuredOutput):
    """结构 agent 输出，主要用于生成新节点和新关系。

    保持与 InspirationOutput / ResearchOutput 相同的字段集合，
    这样 chat_assembler 可以统一处理 cited_node_ids，而无需区分 intent。
    """

    reasoning: str
    summary: str
    referenced_node_ids: list[str] = Field(default_factory=list)
    proposed_changes: list[ProposedChange] = Field(default_factory=list)


LikelihoodLiteral = Literal["high", "medium", "low"]
"""模拟模式中的分支可能性（兼容现有设定）。"""


class SimulationBranch(_LlmStructuredOutput):
    """单个假设方向。"""

    scenario: str
    likelihood: LikelihoodLiteral
    downstream_impacts: list[str] = Field(default_factory=list)
    affected_node_ids: list[str] = Field(default_factory=list)


class SimulationOutput(_LlmStructuredOutput):
    """模拟 agent 输出，列出多个方向供用户选择，绝不写入画布。"""

    reasoning: str
    branches: list[SimulationBranch] = Field(default_factory=list)


class ChatAssemblerOutput(_LlmStructuredOutput):
    """聊天组装器输出，将结构化 agent 结果转换为自然语言气泡。

    ``staging_summary`` 是可选的一行摘要，会渲染在气泡尾部，告诉用户
    “我将修改 N 处”，并与 staging 面板形成上下呼应。
    """

    reply_text: str
    cited_node_ids: list[str] = Field(default_factory=list)
    staging_summary: str = ""
    web_sources: list[WebSourceItem] = Field(default_factory=list)


class ChatMetadataOutput(_LlmStructuredOutput):
    """chat_assembler 第二步：生成 reply_text 后单独抽取元数据。

    拆分目的：reply_text 使用 token 流式生成，无法使用 function_calling；
    而 cited_node_ids / staging_summary 等元数据不需要流式返回，可以通过一次
    结构化调用返回。两次调用合起来仍形成完整的 ChatAssemblerOutput，
    对外契约不变。
    """

    cited_node_ids: list[str] = Field(default_factory=list)
    staging_summary: str = ""

    
class SummaryOutput(_LlmStructuredOutput):
    """摘要压缩节点的结构化输出。

    ``key_facts`` 让 LLM 显式列出“这段对话锁定的关键事实”，既能确保压缩不漏
    信息，也方便上层在调试或 UI 提示中获取“这份摘要保留了哪些信息”。
    """

    summary: str
    key_facts: list[str] = Field(default_factory=list)


# --- first_revision 第 4 阶段：后台 B-agent 输出契约 ---

EntityTypeLiteral = Literal["character", "world", "plot"]
"""structured_extractor 抽取的实体类型；会映射到子图分区和 node_type。"""


class StructuredEntity(_LlmStructuredOutput):
    """从自由对话中抽取出的实体（Character / Worldbuilding / Plot）。"""

    type: EntityTypeLiteral
    name: str
    attributes: dict[str, str] = Field(default_factory=dict)


class StructuredRelation(_LlmStructuredOutput):
    """实体之间的关系；source_name / target_name 引用本轮抽取出的实体名。"""

    source_name: str
    target_name: str
    label: str = ""


class DeferredField(_LlmStructuredOutput):
    """尚未填写且值得后续追问的字段（输入 question_planner）。"""

    entity: str
    field: str


class StructuredExtractionOutput(_LlmStructuredOutput):
    """structured_extractor（B-agent 之一）的结构化输出。"""

    reasoning: str = ""
    entities: list[StructuredEntity] = Field(default_factory=list)
    relations: list[StructuredRelation] = Field(default_factory=list)
    deferred_fields: list[DeferredField] = Field(default_factory=list)


class QuestionPlannerOutput(_LlmStructuredOutput):
    """question_planner（另一个 B-agent）的结构化输出。"""

    reasoning: str = ""
    next_question: str = ""
    target_field: str = ""


WorkspaceOutputLiteral = Literal["search", "rag", "question", "feedback"]
"""被动工作区 agent 的输出类型；前端据此分发到不同卡片。"""


class WorkspaceInspirationOutput(_LlmStructuredOutput):
    """轻量工作区灵感 agent 的结构化输出（second_revision 变更 B / W5）。

    被动响应：只有用户在底部对话框发送消息（可选引用节点）时，才生成单张卡片。
    """

    reasoning: str = ""
    type: WorkspaceOutputLiteral = "feedback"
    content: str = ""


class SeedOutput(_LlmStructuredOutput):
    """项目 seed 压缩输出（first_revision 第 5 阶段）。

    seed_compressor 会把项目当前状态压缩成这个结构化快照，持久化到
    ProjectSeedORM，供 Chat Agent 启动时注入（约 500 tokens 量级）。
    """

    worldview_summary: str = ""
    main_characters: list[str] = Field(default_factory=list)
    plot_outline: str = ""
    style_notes: str = ""
