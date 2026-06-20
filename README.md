# OC Creative Assistant

OC Creative Assistant 是一个面向原创角色、剧情和世界观创作的 AI 工作台。系统提供可视化画布、RAG 项目记忆、多 Agent 协作、结构化画布变更，以及独立的角色 LoRA 微调支线。

## 目录结构

```text
frontend/                 Vue 3 + Vite 前端
backend/                  FastAPI 主后端、RAG、多 Agent 编排
electron/                 Electron 桌面壳与打包配置
role_finetune_service/    独立 GPU/AutoDL 角色 LoRA 微调服务
scripts/                  桌面开发与构建脚本
```

`role_finetune_service/` 是独立远程训练服务，不会进入 Electron 桌面端打包产物。

## 环境配置方法

### 1. 安装 Node.js 依赖

在项目根目录执行：

```powershell
npm install
npm --prefix frontend install
npm --prefix electron install
```

### 2. 安装后端 Python 依赖

建议在项目根目录创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 3. 配置主后端环境变量

参考 `backend/.env.example` 创建 `backend/.env`。常用配置包括：

```env
OC_LLM_PROVIDER=openai
OC_LLM_BASE_URL=https://openrouter.ai/api/v1
OC_LLM_API_KEY=your-api-key
OC_LLM_MODEL=deepseek-v4-flash

OC_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OC_EMBEDDING_API_KEY=your-dashscope-api-key
OC_EMBEDDING_MODEL=text-embedding-v4
OC_EMBEDDING_DIMENSION=1024

OC_ROLE_FINETUNE_BASE_URL=http://127.0.0.1:9100
```

如果暂时不使用角色微调服务，可以不配置 `OC_ROLE_FINETUNE_BASE_URL`，前端会显示训练服务离线并保留资料兜底对话。

## 如何运行

### 前后端开发模式

终端 1：启动后端。

```powershell
.\.venv\Scripts\Activate.ps1
npm run backend:dev
```

后端默认监听：

```text
http://127.0.0.1:9000
```

终端 2：启动前端。

```powershell
npm run frontend:dev
```

前端默认监听：

```text
http://127.0.0.1:5174
```

### 桌面端开发模式

```powershell
.\.venv\Scripts\Activate.ps1
npm run dev:desktop
```

该脚本会协调前端、后端和 Electron。开发时也可以先分别启动 `frontend:dev` 与 `backend:dev`，再运行 `dev:desktop`。

### 局域网访问

后端需要监听 `0.0.0.0`：

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 9000 --app-dir backend
```

前端需要监听 `0.0.0.0`：

```powershell
$env:FRONTEND_DEV_HOST="0.0.0.0"
$env:VITE_BACKEND_URL="http://你的局域网IP:9000"
npm --prefix frontend run dev
```

其他设备访问：

```text
http://你的局域网IP:5174
```

### 桌面端构建

```powershell
.\.venv\Scripts\Activate.ps1
npm run build:desktop
```

构建产物位于：

```text
electron/dist/
```

包括 Windows 安装包、便携版和未压缩目录。

### 远程角色微调服务

角色 LoRA 微调服务需要在 GPU/AutoDL 环境中单独启动。详见：

```text
role_finetune_service/README.md
```

主后端通过 `OC_ROLE_FINETUNE_BASE_URL` 连接它。

## 主要功能

- 可视化创作画布：角色、剧情、世界观节点编辑，关系连线，树状整理。
- RAG 项目记忆：SQLite 图数据作为真值来源，ChromaDB 增量索引，支持 top-k 检索。
- 多 Agent 协作：Research、Inspiration、Structure、Simulation 等专职 Agent 通过 LangGraph 编排。
- ReAct 工具调用：Agent 可主动调用 `search_nodes`、`get_node`、`list_neighbors` 等项目工具收集证据。
- 结构化画布变更：Structure Agent 生成节点/边变更，经过 `boundary_check` 校验后进入暂存或自动应用。
- 流式对话体验：前端展示回复 token、工具轨迹、RAG 证据和 Agent 状态。
- 角色 LoRA 微调：选择自创角色，导出角色快照，生成 Alpaca SFT 数据，远程训练 adapter 并进行角色对话。

## 常用脚本

```powershell
npm run frontend:dev       # 启动前端开发服务器
npm run frontend:build     # 构建前端
npm run backend:dev        # 启动 FastAPI 后端
npm run backend:build      # 构建后端可执行产物
npm run electron:dev       # 启动 Electron
npm run electron:build     # 构建 Electron 子项目
npm run dev:desktop        # 一体化桌面开发
npm run build:desktop      # 完整桌面端打包
```
