# OC Creative Assistant

OC Creative Assistant 是一个面向原创角色、世界观和剧情设定的创作辅助系统。它提供可视化项目工作台、知识库/RAG、Agent 写作辅助，以及一个项目级的“角色模型”工作流：根据 OC 设定生成 LoRA 数据集，下载小模型，在具备 CUDA 条件的机器上微调，并在独立页面中与微调后的角色模型聊天。

## 功能概览

- 项目工作台：管理角色、剧情、世界观等节点和关系。
- AI 聊天与 Agent：连接项目知识库，支持基于设定的问答、补全和结构化创作建议。
- 本地知识库：后端使用 SQLite 保存业务数据，使用 ChromaDB 做向量检索。
- 角色模型工作台：检测服务器硬件，推荐 ModelScope 小模型，生成/编辑 LoRA SFT 数据集，下载模型并启动本地微调。
- 角色模型聊天：在独立页面中与训练后的角色模型聊天；若本地模型不可用，会回退到配置的主 AI API，并保留聊天记录。
- 桌面端：Electron 封装前端和后端，支持开发模式与 Windows 打包。

## 技术栈

- 前端：Vue 3、TypeScript、Vite。
- 后端：FastAPI、SQLAlchemy、SQLite、ChromaDB、LangChain、LangGraph。
- 大模型接入：OpenAI 兼容接口，可连接 DeepSeek、通义、OpenAI 或其他兼容服务。
- LoRA 模块：ModelScope、Transformers、Datasets、PEFT、Accelerate、PyTorch。
- 桌面端：Electron、electron-builder。

## 重要限制：CUDA 与 LoRA

没有 CUDA 显卡的部署环境不能使用本地 LoRA 微调模块。

更准确地说，本地 LoRA 训练需要同时满足：

- 后端部署机器有 NVIDIA GPU。
- 已安装可用的 NVIDIA 驱动。
- 当前 Python 环境中的 PyTorch 是匹配驱动/CUDA 版本的 CUDA 版 PyTorch。
- 显存、内存和磁盘空间足够承载推荐的小模型、训练数据和 LoRA adapter。

如果机器没有 CUDA，项目仍然可以启动，普通 AI 聊天、知识库、Agent、模型推荐、数据集生成/编辑等功能仍可使用；但“开始训练”会被阻断，本地 LoRA 推理也无法作为主要路径使用。此时角色模型聊天会使用主 AI API 做风格兜底。

项目提供了一个 CUDA 12.8 的可选安装文件：

```powershell
pip install -r backend/requirements-cuda-cu128.txt
```

只有当机器驱动支持 CUDA 12.8 或兼容运行时，才应安装上面的文件。其他 CUDA 版本请按 PyTorch 官方安装命令替换对应 wheel。

## 目录结构

```text
oc-creative-assistant/
  backend/                 FastAPI 后端、数据模型、Agent、RAG、LoRA 服务
    app/
    data/                  默认本地运行数据目录，不应提交到 Git
    requirements.txt
    requirements-cuda-cu128.txt
  frontend/                Vue/Vite 前端
  electron/                Electron 桌面端
  scripts/                 开发和打包脚本
  package.json             根项目脚本入口
```

## 环境准备

建议使用 Node.js 20+ 和 Python 3.11。后端推荐用 Conda 单独建环境：

```powershell
cd F:\Development\WebDevelopment\oc-assistant\oc-creative-assistant
conda create -n oc-assistant python=3.11 -y
conda activate oc-assistant
pip install -r backend/requirements.txt
```

如果要在 CUDA 机器上启用本地 LoRA 训练，再安装匹配 CUDA 的 PyTorch，例如本项目提供的 CUDA 12.8 配置：

```powershell
pip install -r backend/requirements-cuda-cu128.txt
```

前端、根脚本和 Electron 依赖分别安装：

```powershell
npm install
npm --prefix frontend install
npm --prefix electron install
```

## 后端配置

后端会读取 `backend/.env` 和系统环境变量。常用配置如下：

```env
OC_LLM_PROVIDER=openai
OC_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
OC_LLM_API_KEY=your-api-key
OC_LLM_MODEL=deepseek/deepseek-chat

OC_EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1
OC_EMBEDDING_API_KEY=your-api-key
OC_EMBEDDING_MODEL=text-embedding-v4
OC_EMBEDDING_DIMENSION=1024

OC_WEB_SEARCH_API_KEY=your-web-search-key
OC_CREATIVE_DATA_DIR=F:\path\to\persistent\data
```

未配置真实 LLM 或 embedding 服务时，部分能力会降级或不可用；生产/展示部署建议完整配置。

## 开发启动

所有命令在项目根目录 `oc-creative-assistant` 下运行。

启动后端：

```powershell
conda activate oc-assistant
npm run backend:dev
```

默认监听 `http://127.0.0.1:9000`。

启动前端：

```powershell
npm run frontend:dev
```

Vite 会给出前端访问地址。若需要让局域网其他设备访问，前端需要使用 `--host 0.0.0.0` 启动，并确保后端监听地址、防火墙和 `VITE_BACKEND_URL` 配置正确。

启动 Electron 开发模式：

```powershell
npm run dev:desktop
```

## 常用脚本

```powershell
npm run frontend:dev      # 启动前端开发服务
npm run frontend:build    # 类型检查并构建前端
npm run backend:dev       # 启动 FastAPI 后端
npm run backend:build     # 为桌面端构建后端产物
npm run electron:dev      # 启动 Electron 子项目开发模式
npm run electron:build    # 构建 Electron 子项目
npm run dev:desktop       # 协调前端、后端、Electron 的桌面端开发流程
npm run build:desktop     # 构建完整桌面端
```

## 角色模型工作流

1. 在“角色模型工作台”检测后端机器硬件。
2. 后端根据显存、内存、磁盘、CUDA 状态和项目设定推荐 ModelScope 模型及 LoRA 参数。
3. 前端把推荐模型填入模型 ID 输入框，用户可打开 ModelScope 页面确认模型。
4. 根据 OC 角色介绍和项目知识库生成 LoRA 数据集。
5. 用户在前端分页编辑、启用/禁用样本，并保存数据集。
6. 后端下载模型并启动 LoRA 微调。
7. 微调完成后，在同一页面的独立聊天区与角色模型聊天。

训练前系统会检查三个前置条件：启用样本不少于 200 条、当前模型 ID 对应的基础模型已经下载完成、后端机器满足 CUDA/显存/磁盘要求。任一条件不满足时，“开始训练”会被阻断并在页面中给出原因，避免后台长时间卡住或训练到一半失败。

如果模型或 adapter 已经下载/训练过，下次打开角色模型页面时会自动恢复状态；训练产物存在时默认进入聊天界面，用户仍可点击“新训练模型”回到完整训练流程。如果记录存在但本地文件已经被删除、数据目录迁移或换了机器，后端会把对应任务标记为失败并允许重新下载或重新训练。

角色模型聊天有两种运行模式：`local_lora` 表示后端正在使用本地基础模型和 LoRA adapter；`api_fallback` 表示训练产物尚未就绪，或当前机器缺少 CUDA/推理依赖，系统会用主 AI API 结合数据集和知识库做角色风格兜底。

角色模型聊天记录会保存到现有 `chat_sessions` / `chat_messages` 表中，并与普通 AI 聊天隔离。清空按钮会同步删除后端保存的角色模型聊天历史。

## 数据与可移植性

默认开发数据写入 `backend/data`，包括 SQLite 数据库、ChromaDB 索引、下载模型、LoRA 数据集和训练产物。桌面端打包时可通过 `OC_CREATIVE_DATA_DIR` 指定持久化目录。

请不要把 `backend/data`、模型权重、训练产物、`.env`、本地 Conda 环境或缓存目录提交到 Git。项目代码不应依赖某一台机器的绝对路径；部署时通过环境变量和依赖文件配置。

## 故障排查

- 提示“检测到 NVIDIA GPU，但当前 PyTorch 未启用 CUDA”：当前环境装的是 CPU 版 PyTorch，需要安装与驱动匹配的 CUDA 版 PyTorch。
- 没有 NVIDIA GPU：可以正常使用项目主体功能，但不能进行本地 LoRA 微调。
- “开始训练”按钮不可用：先确认启用样本达到 200 条、模型 ID 与已下载模型一致，并已通过 CUDA 硬件检查。
- ModelScope 下载失败：检查网络、磁盘空间、模型 ID 是否形如 `namespace/model-name`。
- 前端访问不到后端：检查后端是否在 `9000` 端口运行，必要时设置 `VITE_BACKEND_URL`。
- 角色模型聊天看起来不是本地模型：如果 LoRA adapter 尚未训练完成或本地推理依赖不可用，系统会回退到主 AI API。
