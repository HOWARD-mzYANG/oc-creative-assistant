# oc-creative-assistant
OC 创意助手系统

## 安装依赖

### 前端依赖

前端依赖由 `frontend/package.json` 维护。进入 `frontend` 目录并安装：

```powershell
cd frontend
npm install
```

安装完成后，可以回到项目根目录：

```powershell
cd ..
```

### Electron 依赖

Electron 子项目由 `electron/package.json` 维护。按以下顺序安装依赖：

```powershell
cd electron
npm install
```

随后回到项目根目录：

```powershell
cd ..
```

### 后端依赖

建议先在项目根目录创建 Python 虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

后端依赖由 `backend/requirements.txt` 维护。激活虚拟环境后安装：

```powershell
pip install -r backend/requirements.txt
```

## 常用脚本

以下所有命令都在项目根目录运行，也就是包含根级 `package.json` 的目录。

任何启动或构建后端的命令，都需要在已激活后端 Python 环境的终端中运行。如果打开了新终端，请先再次激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
npm run frontend:dev
```

启动前端 Vite 开发服务器。该命令会进入 `frontend` 子项目并运行 `npm run dev`。

```powershell
npm run frontend:build
```

构建前端产物。该命令会进入 `frontend` 子项目，执行类型检查和 Vite 构建。

```powershell
npm run backend:dev
```

启动后端 FastAPI 开发服务器，监听 `127.0.0.1:9000`。建议运行前先激活 Python 虚拟环境。

例如：

```powershell
.\.venv\Scripts\Activate.ps1
npm run backend:dev
```

```powershell
npm run backend:build
```

运行后端构建脚本 `scripts/build-backend.mjs`，为桌面端打包流程准备后端产物。

```powershell
npm run electron:dev
```

以开发模式启动 Electron 子项目。请先完成上方“Electron 依赖”部分的安装。

```powershell
npm run electron:build
```

构建 Electron 子项目。请先完成上方“Electron 依赖”部分的安装。

```powershell
npm run dev:desktop
```

启动桌面端一体化开发流程，由 `scripts/dev-desktop.mjs` 协调前端、后端和 Electron 开发进程。

如果该脚本需要自动启动后端，请在已激活后端 Python 环境的终端中运行。

**推荐做法**：先在两个独立终端中分别运行 `npm run frontend:dev` 和 `npm run backend:dev`（后端终端需要激活虚拟环境）。等 Vite 和 FastAPI 就绪后，再运行 `npm run dev:desktop`。该脚本会复用已经运行的前端和后端，避免重复启动；如果没有手动启动，它也会在打开 Electron 前自动拉起前端和后端。

```powershell
npm run build:desktop
```

运行完整的桌面端构建流程，由 `scripts/build-desktop.mjs` 协调前端、后端和 Electron 的打包步骤。

构建完成后，桌面端产物会写入 `electron/dist`：

- `electron/dist/OC Creative Assistant Setup 0.1.0.exe`：Windows NSIS 安装包，可分发给用户安装。
- `electron/dist/OC Creative Assistant 0.1.0.exe`：Windows 便携版可执行文件，无需安装即可直接运行。
- `electron/dist/win-unpacked/OC Creative Assistant.exe`：未打包压缩的应用可执行文件，适合构建后做本地快速冒烟测试。
- `electron/dist/OC Creative Assistant Setup 0.1.0.exe.blockmap`、`builder-debug.yml` 和 `builder-effective-config.yaml`：Electron Builder 生成的构建元数据，不是主要面向用户的可执行文件。

其中 `0.1.0` 版本号来自 `electron/package.json`，因此 Electron 包版本变化时，这些文件名也会随之变化。
