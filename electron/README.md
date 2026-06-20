# Electron

`electron/` 是 OC Creative Assistant 的桌面端壳，负责启动桌面窗口、连接前端资源、管理打包后的本地后端进程，并生成 Windows 桌面应用。

## 环境配置方法

安装 Electron 子项目依赖：

```powershell
cd electron
npm install
```

开发模式依赖：

- 前端开发服务器通常运行在 `http://127.0.0.1:5174`。
- 后端开发服务器通常运行在 `http://127.0.0.1:9000`。
- 一体化脚本由根目录 `scripts/dev-desktop.mjs` 协调。

打包模式依赖：

- `.bundle/frontend`：由根目录构建脚本放入前端构建产物。
- `.bundle/backend`：由根目录构建脚本放入后端可执行产物。

不要手动维护 `.bundle/`，它是构建流程生成的临时目录。

## 如何运行

推荐从项目根目录运行：

```powershell
npm run dev:desktop
```

也可以只启动 Electron 子项目：

```powershell
npm --prefix electron run dev
```

构建完整桌面端：

```powershell
npm run build:desktop
```

仅构建 Electron 子项目：

```powershell
npm --prefix electron run build
```

构建产物位于：

```text
electron/dist/
```

常见产物：

- `OC Creative Assistant Setup 版本号.exe`：Windows 安装包。
- `OC Creative Assistant 版本号.exe`：Windows 便携版。
- `win-unpacked/OC Creative Assistant.exe`：未压缩应用目录，适合冒烟测试。

## 主要功能

- 创建 Electron BrowserWindow 并加载前端页面。
- 开发模式下连接 Vite 前端与 FastAPI 后端。
- 打包模式下启动随应用携带的后端可执行文件。
- 通过 `preload.cjs` 暴露必要的桌面端配置能力。
- 使用 `electron-builder` 生成 Windows NSIS 安装包和 portable 便携版。

## 注意事项

- 远程角色微调服务不属于 Electron 打包内容。
- `role_finetune_service/workspace`、模型权重、训练数据和 adapter 不应进入桌面端安装包。
- 如果开发时端口被占用，优先检查前端 `5174` 和后端 `9000`。
