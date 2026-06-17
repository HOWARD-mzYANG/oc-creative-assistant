# 角色微调服务

这是独立部署在 GPU/服务器侧的角色 LoRA 微调服务。主桌面 app 只负责导出角色快照、
查看任务状态和发起角色对话；数据集、训练日志、adapter 和模型 API 都由这个服务维护。

## 本地运行

```powershell
cd role_finetune_service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9100
```

主后端通过下面的环境变量连接训练服务：

```powershell
$env:OC_ROLE_FINETUNE_BASE_URL="http://127.0.0.1:9100"
```

## 常用环境变量

- `ROLE_FINETUNE_WORKSPACE`：任务、数据集、日志和 adapter 的输出目录，默认是 `role_finetune_service/workspace`。
- `ROLE_TRAINING_DRY_RUN`：设为 `true` 时只生成数据和配置，不调用 LLaMA-Factory，适合本地快速演示。
- `ROLE_LLAMAFACTORY_BIN`：训练命令，默认是 `llamafactory-cli`。
- `ROLE_LLAMAFACTORY_DIR`：可选，LLaMA-Factory 仓库目录，会作为训练命令的工作目录。
- `ROLE_BASE_MODEL`：基础模型，默认是 `Qwen/Qwen2.5-1.5B-Instruct`。
- `ROLE_SAMPLE_COUNT`：默认训练样本数，默认 240；代码会保证至少生成 200 条。
- `ROLE_QUANTIZATION_BIT`：QLoRA 量化位数，默认 `4`；4-bit 训练需要安装 `bitsandbytes`。设为 `0` 可关闭量化，改用普通 LoRA。
- `ROLE_TRAINING_FP16`：是否使用 fp16，默认 `true`，适合多数 AutoDL 显卡。
- `ROLE_TRAINING_BF16`：是否使用 bf16，默认 `false`；只有确认显卡和 PyTorch CUDA 环境支持 bf16 时再开启。
- `ROLE_MODEL_API_BASE_URL`：可选，已加载 adapter 的 OpenAI-compatible 模型服务地址，例如 `llamafactory-cli api`。
- `ROLE_MODEL_API_KEY`：可选，模型服务 API key。
- `ROLE_MODEL_API_NAME`：对话接口使用的模型名，默认是 `role-lora`。
- `ROLE_DATASET_API_BASE_URL`：可选，训练数据生成使用的 OpenAI-compatible API 地址；配置后 240 条 SFT 样本必须由这组 API 生成，失败则任务失败。
- `ROLE_DATASET_API_KEY`：可选，训练数据生成 API key。
- `ROLE_DATASET_API_MODEL`：训练数据生成使用的模型名，默认回退到 `ROLE_MODEL_API_NAME` 或 `role-data-generator`。
- `ROLE_DATASET_API_BATCH_SIZE`：每次 API 调用生成多少条样本，默认 20，最大 40。
- `ROLE_DATASET_API_TIMEOUT`：每个批次请求的超时时间秒数，默认 120。
- `ROLE_DATASET_API_TEMPERATURE`：训练数据生成温度，默认 0.8。

## 产物说明

每个训练任务都会写入独立目录：

- `snapshot.json`：主后端导出的角色快照。
- `material_brief.json`：主后端资料 agent 整理后的角色训练档案。
- `dataset/*.json`：中文 Alpaca SFT 训练数据。
- `dataset/dataset_info.json`：LLaMA-Factory 自定义数据集索引。
- `train.yaml`：LLaMA-Factory 训练配置。
- `train.log`：训练日志。
- `adapter/`：LoRA adapter 输出目录。
- `chat_history.jsonl`：用户选择该模型对话时的远程聊天记录。

`workspace/` 已加入根目录 `.gitignore`，不会被提交，也不会进入 Electron 打包。

## 角色模型选择和聊天记录

主后端进入角色模型页时会先调用训练服务的任务列表接口，查询当前项目和角色是否
已经存在训练完成的模型。前端会默认选择最近一个已完成任务；如果没有完成任务，
则显示最近的排队/训练/失败任务，并允许用户重新整理资料并训练。

角色对话会绑定到当前选择的训练任务。训练服务会把每轮用户消息和角色回复追加到
该任务目录下的 `chat_history.jsonl`，前端再次选择同一个模型时会读取并展示历史。
