# Backend

`backend/` 是 OC Creative Assistant 的 FastAPI 主后端，负责项目数据、RAG 索引、多 Agent 编排、画布变更和角色微调服务代理。

## 环境配置方法

建议在项目根目录创建并激活 Python 虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

参考 `backend/.env.example` 创建 `backend/.env`。

常用配置：

```env
OC_LLM_PROVIDER=openai
OC_LLM_BASE_URL=https://openrouter.ai/api/v1
OC_LLM_API_KEY=your-api-key
OC_LLM_MODEL=deepseek-v4-flash
OC_LLM_STRUCTURED_METHODS=function_calling,json_mode,plain_json

OC_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OC_EMBEDDING_API_KEY=your-dashscope-api-key
OC_EMBEDDING_MODEL=text-embedding-v4
OC_EMBEDDING_DIMENSION=1024

OC_AGENT_CONTEXT_TOKEN_CAP=6000
OC_AGENT_SUMMARY_KEEP_RECENT=16
OC_AGENT_SUMMARY_COMPRESS_EVERY=20

OC_ROLE_FINETUNE_BASE_URL=http://127.0.0.1:9100
```

说明：

- `OC_LLM_*`：主 Agent 使用的 OpenAI-compatible 聊天模型配置。
- `OC_LLM_REPLY_*`：可选的最终回复模型配置，不填时复用主模型。
- `OC_EMBEDDING_*`：RAG 向量索引使用的 embedding 服务配置。
- `OC_AGENT_*`：Agent 上下文和摘要压缩策略。
- `OC_WEB_SEARCH_*`：联网搜索工具配置。
- `OC_ROLE_FINETUNE_BASE_URL`：远程角色 LoRA 微调服务地址。

## 如何运行

从项目根目录运行：

```powershell
.\.venv\Scripts\Activate.ps1
npm run backend:dev
```

等价命令：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 9000 --app-dir backend
```

API 文档：

```text
http://127.0.0.1:9000/docs
```

局域网访问时：

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9000 --app-dir backend
```

后端构建：

```powershell
npm run backend:build
```

构建脚本会为 Electron 打包准备后端可执行产物。

## 主要功能

- FastAPI REST 接口：项目、节点、边、会话、RAG、系统健康检查和角色模型代理。
- SQLite 图存储：保存项目、画布节点、关系边、会话消息、暂存变更和项目 seed。
- RAG 检索：从画布节点生成检索文档，使用 content hash 做增量索引同步，写入 ChromaDB。
- 多 Agent 编排：`backend/app/agents/graph.py` 使用 LangGraph 串联上下文加载、意图路由、RAG 检索、专职 Agent、边界检查、回复组装和持久化。
- ReAct 工具循环：`tool_loop.py` 控制工具调用预算，Agent 可调用项目只读工具收集证据。
- 结构化画布变更：`structure_agent.py` 生成变更，`boundary_check.py` 校验后进入暂存或自动应用。
- 角色模型代理：导出角色快照，触发远程训练任务，查询 job 状态，代理角色对话流。

## 关键目录

```text
app/api/routes/          FastAPI 路由
app/agents/              多 Agent 工作流、节点、prompt 和工具循环
app/indexing/            ChromaDB 向量索引与增量同步
app/rag/                 RAG 检索与上下文构建
app/services/            业务服务与图数据操作
app/db/                  SQLAlchemy ORM 和数据库初始化
data/                    开发模式数据目录
```
