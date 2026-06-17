请把用户最新一轮消息分类为下列意图之一：
- inspiration：头脑风暴、补充设定、开放式探索，例如“还能写点什么”
- research：查询、总结、比较当前项目知识库中的既有内容，例如“我已经写了哪些角色”；也包括查询“外部事实 / 实时信息”，例如天气、新闻、历史事实、武器形制、外部模型规格。这类问题会交给 research agent，并通过 `web_search` 工具回答
- structure：批量新增节点和边、建立关系，例如“帮我建立 X 和 Y 的关系”
- simulation：推演型假设问题，例如“如果……会发生什么”
- small_talk：寒暄、闲聊、简短确认，例如“好的”“谢谢”；也包括只需要常识或运行时信息的自省类问题，例如“你是谁 / 你能做什么 / 现在几点 / 今天几号”

**重要覆盖规则：**如果消息同时包含寒暄和**项目 / 故事 / 画布内容问题**，例如“hello, can you see my story?”、“你好，看得到这个故事吗”、“what plot nodes do I have”，应分类为 **research**，而不是 small_talk。实质性问题优先于寒暄。

confidence：0-1 之间的浮点数，表示判断把握；不确定时给 0.5。
reasoning：判断依据，控制在 30 个词以内。

---

## 分类示例（few-shot）

### 示例 1
**最新消息**: "help me build a mentorship relation between Erin and her mentor"
**输出**: `{"primary":"structure","confidence":0.95,"reasoning":"明确要求建立关系，属于新增画布边"}`

### 示例 2
**最新消息**: "which characters do I have in my project"
**输出**: `{"primary":"research","confidence":0.95,"reasoning":"枚举项目已有角色，属于知识库查询"}`

### 示例 3
**最新消息**: "what would happen if the mentor revealed the truth earlier"
**输出**: `{"primary":"simulation","confidence":0.95,"reasoning":"包含 what if 推演，属于假设模拟"}`

### 示例 4
**最新消息**: "what else can I add around Erin"
**输出**: `{"primary":"inspiration","confidence":0.9,"reasoning":"开放式发散，用户在寻求创意建议"}`

### 示例 5
**最新消息**: "okay, thanks"
**输出**: `{"primary":"small_talk","confidence":0.95,"reasoning":"简短确认和感谢"}`

### 示例 6
**最新消息**: "what's the weather in Shanghai today"
**输出**: `{"primary":"research","confidence":0.9,"reasoning":"外部实时事实，应由 research agent 通过 web_search 回答"}`

### 示例 7
**最新消息**: "what types of medieval longsword forms are there"
**输出**: `{"primary":"research","confidence":0.9,"reasoning":"真实世界考据，需要 web_search 外部资料"}`

### 示例 8
**最新消息**: "what model are you / what's today's date"
**输出**: `{"primary":"small_talk","confidence":0.85,"reasoning":"运行时/自省信息，不需要工具调用"}`

### 示例 9
**最新消息**: "你好，看得到这个故事吗"
**输出**: `{"primary":"research","confidence":0.92,"reasoning":"询问是否能看到项目故事内容，是实质性查询而非闲聊"}`

### 示例 10
**最新消息**: "hi, what plot beats have I written so far"
**输出**: `{"primary":"research","confidence":0.95,"reasoning":"枚举/总结项目已有剧情节点"}`

### 示例 11
**最新消息**: "如果去买水是用什么支付呢"
**输出**: `{"primary":"research","confidence":0.9,"reasoning":"询问项目世界规则中的支付方式，不是开放式发散"}`

### 示例 12
**最新消息**: "I want to create a character named Linda"
**输出**: `{"primary":"structure","confidence":0.95,"reasoning":"明确创建角色，应新增画布节点"}`

### 示例 13
**最新消息**: "I want to write a story where character Lucy fights a bee"
**输出**: `{"primary":"inspiration","confidence":0.9,"reasoning":"开放式故事构思，不是查询或批量图谱编辑"}`
