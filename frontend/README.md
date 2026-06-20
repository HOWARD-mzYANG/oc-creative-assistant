# Frontend

`frontend/` 是 OC Creative Assistant 的 Vue 3 前端，负责项目首页、工作区、画布、Agent 对话界面和角色模型工作室。

## 环境配置方法

安装依赖：

```powershell
cd frontend
npm install
```

常用环境变量：

```powershell
$env:VITE_BACKEND_URL="http://127.0.0.1:9000"
$env:FRONTEND_DEV_HOST="127.0.0.1"
$env:FRONTEND_DEV_PORT="5174"
```

说明：

- `VITE_BACKEND_URL`：前端请求 FastAPI 主后端的地址。未设置时，浏览器环境会默认使用当前 hostname 的 `9000` 端口。
- `FRONTEND_DEV_HOST`：Vite 开发服务器监听地址。局域网访问时设为 `0.0.0.0`。
- `FRONTEND_DEV_PORT`：Vite 开发服务器端口，默认 `5174`。

## 如何运行

开发模式：

```powershell
npm run dev
```

构建：

```powershell
npm run build
```

预览构建产物：

```powershell
npm run preview
```

也可以在项目根目录运行：

```powershell
npm run frontend:dev
npm run frontend:build
```

## 主要功能

- 项目库与工作区导航。
- Vue Flow 可视化画布，支持节点编辑、关系连线、拖拽保存和树状整理。
- 角色、剧情、世界观等节点详情展示与编辑。
- 多 Agent 对话界面，支持流式回复、RAG 证据、工具调用轨迹和思考状态展示。
- RoleModelStudio 角色模型工作室，支持资料快照、手动资料整理、训练任务启动、日志查看、已有模型选择和角色对话。
- 与 Electron 桌面壳协作，在打包模式下加载本地后端与前端静态资源。
