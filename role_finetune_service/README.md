# 角色微调服务

`role_finetune_service/` 是独立部署在 GPU/服务器侧的角色 LoRA 微调服务。主桌面 app 只负责导出角色快照、查看任务状态和发起角色对话；数据集、训练日志、adapter 和模型 API 都由这个服务维护。

该目录不进入 Electron 打包流程。

## 环境配置方法

### 本地快速环境

```powershell
cd role_finetune_service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

本地没有 GPU 或 LLaMA-Factory 时，可以打开干跑模式：

```powershell
$env:ROLE_TRAINING_DRY_RUN="true"
```

### AutoDL / GPU 环境

推荐使用已安装 LLaMA-Factory 的 conda 环境：

```bash
conda activate /root/autodl-tmp/conda_envs/llamafactory311
cd /root/autodl-tmp/oc-creative-assistant/role_finetune_service
```

常用环境变量：

```bash
export ROLE_BASE_MODEL=/root/autodl-tmp/models/Qwen2.5-1.5B-Instruct
export ROLE_FINETUNE_WORKSPACE=/root/autodl-tmp/oc-role-ft-workspace
export ROLE_LLAMAFACTORY_BIN=/root/autodl-tmp/conda_envs/llamafactory311/bin/llamafactory-cli
export ROLE_LLAMAFACTORY_DIR=/root/autodl-tmp/LLaMA-Factory
export ROLE_MODEL_API_AUTO_START=true
export ROLE_MODEL_API_PORT=8000
```

如果需要使用模型 API 生成训练样本：

```bash
export ROLE_DATASET_API_BASE_URL=https://your-openai-compatible-api/v1
export ROLE_DATASET_API_KEY=your-api-key
export ROLE_DATASET_API_MODEL=deepseek-v4-flash
```

主后端通过以下变量连接本服务：

```env
OC_ROLE_FINETUNE_BASE_URL=http://127.0.0.1:9100
```

## 如何运行

本地或服务器启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 9100
```

健康检查：

```bash
curl http://127.0.0.1:9100/health
```

如果模型 API 端口被占用，可以换端口：

```bash
export ROLE_MODEL_API_PORT=8001
export ROLE_MODEL_API_BASE_URL=http://127.0.0.1:8001
uvicorn app.main:app --host 0.0.0.0 --port 9100
```

如果已经手动启动固定模型 API，可以关闭自动模式：

```bash
export ROLE_MODEL_API_AUTO_START=false
export ROLE_MODEL_API_BASE_URL=http://127.0.0.1:8000
```

## 常用环境变量

- `ROLE_FINETUNE_WORKSPACE`：任务、数据集、日志和 adapter 输出目录，默认 `role_finetune_service/workspace`。
- `ROLE_TRAINING_DRY_RUN`：设为 `true` 时只生成数据和配置，不调用 LLaMA-Factory。
- `ROLE_LLAMAFACTORY_BIN`：训练和推理命令，默认 `llamafactory-cli`。
- `ROLE_LLAMAFACTORY_DIR`：LLaMA-Factory 仓库目录，可作为命令工作目录。
- `ROLE_BASE_MODEL`：基础模型路径或 Hugging Face 名称，默认 `Qwen/Qwen2.5-1.5B-Instruct`。
- `ROLE_SAMPLE_COUNT`：默认训练样本数，默认 240，代码保证至少生成 200 条。
- `ROLE_QUANTIZATION_BIT`：QLoRA 量化位数，默认 `4`；设为 `0` 可关闭量化。
- `ROLE_TRAINING_FP16`：是否使用 fp16，默认 `true`。
- `ROLE_TRAINING_BF16`：是否使用 bf16，默认 `false`。
- `ROLE_MODEL_API_AUTO_START`：对话时是否自动启动/切换 `llamafactory-cli api`，默认 `true`。
- `ROLE_MODEL_API_HOST`：自动启动模型 API 的监听地址，默认 `127.0.0.1`。
- `ROLE_MODEL_API_PORT`：自动启动模型 API 的端口，默认 `8000`。
- `ROLE_MODEL_API_STARTUP_TIMEOUT`：等待模型 API 就绪的秒数，默认 `180`。
- `ROLE_MODEL_API_BASE_URL`：模型 API 地址。自动模式下作为内部访问地址；手动模式下表示外部固定 API。
- `ROLE_DATASET_API_BASE_URL`：训练数据生成使用的 OpenAI-compatible API 地址。
- `ROLE_DATASET_API_KEY`：训练数据生成 API key。
- `ROLE_DATASET_API_MODEL`：训练数据生成模型，默认回退到 `ROLE_MODEL_API_NAME` 或 `role-data-generator`。
- `ROLE_DATASET_API_BATCH_SIZE`：每次 API 调用生成样本数量，默认 20，最大 40。
- `ROLE_DATASET_API_TIMEOUT`：每个批次请求超时时间，默认 120 秒。
- `ROLE_DATASET_API_TEMPERATURE`：训练数据生成温度，默认 0.8。

## 主要功能

- 接收主后端导出的角色快照和资料整理稿。
- 为每个角色训练请求创建独立 job，并维护 `queued / running / succeeded / failed` 状态。
- 生成默认约 240 条 Alpaca SFT 格式训练样本。
- 写入 `dataset_info.json` 和 LLaMA-Factory `train.yaml`。
- 调用 `llamafactory-cli train` 进行 LoRA / QLoRA 微调。
- 保存训练日志、数据集、adapter、任务状态和错误信息。
- 角色对话时自动加载或切换对应 LoRA adapter。
- 代理 OpenAI-style `/v1/chat/completions` 流式输出。
- 按 job 保存远程角色聊天历史。

## 训练产物

每个任务都会写入：

```text
workspace/jobs/{job_id}/
  snapshot.json
  material_brief.json
  job.json
  dataset/
    role_{job_id}.json
    dataset_info.json
  train.yaml
  train.log
  adapter/
  chat_api.yaml
  api.log
  chat_history.jsonl
```

说明：

- `snapshot.json`：主后端导出的角色原始快照。
- `material_brief.json`：资料 agent 整理后的角色训练档案。
- `dataset/*.json`：Alpaca SFT 训练数据。
- `dataset_info.json`：LLaMA-Factory 自定义数据集索引。
- `train.yaml`：训练配置。
- `adapter/`：LoRA adapter 输出。
- `chat_api.yaml`：自动启动推理 API 时生成的配置。
- `api.log`：LLaMA-Factory API 加载和推理日志。
- `chat_history.jsonl`：用户与该角色模型的聊天记录。

`workspace/` 已加入根目录 `.gitignore`，不会被提交，也不会进入 Electron 打包。

## 与主系统的关系

主后端负责：

- 从 SQLite 图谱导出角色快照。
- 可选运行资料 agent，整理角色训练档案。
- 通过 `OC_ROLE_FINETUNE_BASE_URL` 创建训练任务、查询状态和代理角色对话。

远程服务负责：

- 生成训练样本。
- 调用 LLaMA-Factory 训练。
- 管理 adapter、日志和聊天历史。
- 加载基础模型和 LoRA adapter，提供角色对话推理。
