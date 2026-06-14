const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')

// 打包模式下 Electron 主进程托管后端进程；开发模式通常复用外部 uvicorn。
let backendProcess = null
const PDF_EXPORT_CHANNEL = 'oc:export-project-pdf'

// 标准化端口输入；无效时回退到默认值。
function resolvePort(rawPort, fallback) {
  const parsedPort = Number(rawPort)

  if (Number.isInteger(parsedPort) && parsedPort > 0) {
    return parsedPort
  }

  return fallback
}

// 解析开发模式下要加载的前端入口 URL。
function resolveRendererUrl() {
  const host = process.env.FRONTEND_DEV_HOST ?? '127.0.0.1'
  const port = process.env.FRONTEND_DEV_PORT ?? '5174'

  return process.env.ELECTRON_RENDERER_URL ?? `http://${host}:${port}`
}

// 根据主机和端口构建本地 HTTP 基础 URL。
function buildHttpUrl(host, port) {
  return `http://${host}:${port}`
}

// 根据后端基础 URL 构建健康检查端点 URL。
function buildHealthUrl(baseUrl) {
  return `${baseUrl.replace(/\/$/, '')}/health`
}

// 检查指定本地端口当前是否可用。
async function isPortFree(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer()

    server.once('error', () => {
      resolve(false)
    })

    server.once('listening', () => {
      server.close(() => resolve(true))
    })

    server.listen(port, host)
  })
}

// 从首选端口开始向上查找可用端口。
async function findAvailablePort(host, preferredPort, maxAttempts = 20) {
  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const candidatePort = preferredPort + offset

    if (await isPortFree(host, candidatePort)) {
      return candidatePort
    }
  }

  throw new Error(
    `无法为 ${host} 找到从 ${preferredPort} 开始的可用端口。`,
  )
}

// 轮询直到指定 HTTP URL 可访问。
async function waitForUrl(url, timeoutMs = 30_000, intervalMs = 500) {
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url)

      if (response.ok) {
        return
      }
    } catch {
      // 持续轮询，直到端点就绪或超时。
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error(`等待 ${url} 超时`)
}

// 解析 resources 中打包前端入口文件的位置。
function getBundledFrontendEntry() {
  return path.join(process.resourcesPath, 'frontend', 'index.html')
}

// 解析 resources 中打包后端可执行文件的位置。
function getBundledBackendExecutable() {
  const executableName = process.platform === 'win32'
    ? 'oc-creative-backend.exe'
    : 'oc-creative-backend'

  return path.join(process.resourcesPath, 'backend', executableName)
}

// 解析开发和打包构建中的桌面应用图标。
function getAppIconPath() {
  const iconPath = path.join(__dirname, 'assets', 'icon.png')

  if (fs.existsSync(iconPath)) {
    return iconPath
  }

  return path.join(__dirname, 'assets', 'logo.png')
}

// 让桌面 PDF 导出不依赖渲染器弹窗权限。
function sanitizePdfFileName(value) {
  const rawName = String(value || 'project').trim() || 'project'
  const safeName = rawName
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '-')
    .replace(/\s+/g, ' ')
    .replace(/[. ]+$/g, '')
    .slice(0, 120) || 'project'

  return safeName.toLowerCase().endsWith('.pdf') ? safeName : `${safeName}.pdf`
}

async function exportHtmlToPdf(parentWindow, payload) {
  if (!payload || typeof payload.html !== 'string') {
    throw new Error('PDF 导出载荷无效。')
  }

  const defaultPath = sanitizePdfFileName(payload.defaultFileName)
  const saveDialogOptions = {
    title: '导出 PDF',
    defaultPath,
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  }
  const saveResult = parentWindow
    ? await dialog.showSaveDialog(parentWindow, saveDialogOptions)
    : await dialog.showSaveDialog(saveDialogOptions)

  if (saveResult.canceled || !saveResult.filePath) {
    return { canceled: true }
  }

  const pdfWindow = new BrowserWindow({
    show: false,
    parent: parentWindow ?? undefined,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  try {
    const htmlUrl = `data:text/html;charset=UTF-8,${encodeURIComponent(payload.html)}`
    await pdfWindow.loadURL(htmlUrl)

    await pdfWindow.webContents.executeJavaScript(
      'document.fonts && document.fonts.ready ? document.fonts.ready.then(() => true) : true',
      true,
    ).catch(() => true)

    const pdf = await pdfWindow.webContents.printToPDF({
      printBackground: true,
      preferCSSPageSize: true,
    })

    await fs.promises.writeFile(saveResult.filePath, pdf)

    return { canceled: false, filePath: saveResult.filePath }
  } finally {
    if (!pdfWindow.isDestroyed()) {
      pdfWindow.close()
    }
  }
}

// 解析打包后端的数据目录；便携版跟随 exe，安装版跟随当前用户。
function resolveBundledBackendDataDir() {
  const portableExecutableDir = process.env.PORTABLE_EXECUTABLE_DIR

  if (portableExecutableDir) {
    return path.join(portableExecutableDir, 'data')
  }

  return app.getPath('userData')
}

// 应用退出时停止已启动的后端进程。
function stopBundledBackend() {
  if (!backendProcess || backendProcess.killed) {
    return
  }

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(backendProcess.pid), '/t', '/f'], { stdio: 'ignore' })
  } else {
    backendProcess.kill('SIGTERM')
  }
}

// 启动打包后的后端，并等待健康检查通过。
async function startBundledBackend() {
  const backendHost = process.env.BACKEND_HOST ?? '127.0.0.1'
  const preferredBackendPort = resolvePort(process.env.BACKEND_PORT, 9000)
  const selectedBackendPort = await findAvailablePort(backendHost, preferredBackendPort)
  const backendUrl = buildHttpUrl(backendHost, selectedBackendPort)
  const backendHealthUrl = buildHealthUrl(backendUrl)
  const executablePath = getBundledBackendExecutable()
  const backendDataDir = resolveBundledBackendDataDir()

  if (!fs.existsSync(executablePath)) {
    throw new Error(`未在 ${executablePath} 找到打包后的后端可执行文件`)
  }

  // 如果端口被占用，后端实际端口可能会变化；最终 URL 会通过 preload 注入前端。
  // Electron 显式传入数据目录，避免后端写入便携版构建的临时解压目录。
  backendProcess = spawn(
    executablePath,
    ['--host', backendHost, '--port', String(selectedBackendPort)],
    {
      stdio: 'ignore',
      windowsHide: true,
      env: {
        ...process.env,
        OC_CREATIVE_DATA_DIR: backendDataDir,
      },
    },
  )

  backendProcess.on('exit', (code, signal) => {
    backendProcess = null

    if (app.isQuitting) {
      return
    }

    const reason = signal ? `信号 ${signal}` : `退出码 ${code ?? 0}`
    console.error(`[electron] 打包后端意外退出（${reason}）`)
  })

  await waitForUrl(backendHealthUrl)

  return backendUrl
}

// 根据开发或打包模式选择合适的运行时配置。
async function resolveRuntimeConfig() {
  if (!app.isPackaged) {
    // 开发模式不自动启动后端；其 URL 由 scripts/dev-desktop.mjs 或外部服务提供。
    return {
      backendUrl: process.env.BACKEND_BASE_URL ?? null,
      rendererUrl: resolveRendererUrl(),
    }
  }

  const backendUrl = await startBundledBackend()

  return {
    backendUrl,
    rendererUrl: null,
  }
}

// 加载开发前端；失败时回退到内联错误页。
async function loadRenderer(mainWindow, rendererUrl) {
  try {
    console.log(`[electron] 正在从 ${rendererUrl} 加载渲染器`)
    await mainWindow.loadURL(rendererUrl)
    console.log('[electron] 渲染器加载成功')
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知渲染器错误'
    const fallbackHtml = `
      <!doctype html>
      <html lang="zh-CN">
        <head>
          <meta charset="UTF-8" />
          <title>渲染器不可用</title>
          <style>
            body {
              margin: 0;
              min-height: 100vh;
              display: grid;
              place-items: center;
              font: 16px/1.5 "Segoe UI", sans-serif;
              background: #f7f2eb;
              color: #2e2419;
            }
            main {
              width: min(640px, calc(100% - 48px));
              padding: 32px;
              border-radius: 24px;
              border: 1px solid rgba(74, 58, 39, 0.12);
              background: rgba(255, 255, 255, 0.95);
              box-shadow: 0 20px 50px rgba(74, 58, 39, 0.1);
            }
            code {
              padding: 0.16rem 0.45rem;
              border-radius: 999px;
              background: rgba(46, 36, 25, 0.07);
            }
          </style>
        </head>
        <body>
          <main>
            <h1>渲染器不可用</h1>
            <p>Electron 无法加载位于 <code>${rendererUrl}</code> 的前端入口。</p>
            <p>详情：${message}</p>
          </main>
        </body>
      </html>
    `

    await mainWindow.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(fallbackHtml)}`)
  }
}

// 判断 URL 是否为外部 HTTP(S) 链接。
function isHttpUrl(url) {
  return /^https?:/i.test(url)
}

// 判断链接是否仍属于当前前端源。
function hasSameOrigin(url, rendererOrigin) {
  try {
    return new URL(url).origin === rendererOrigin
  } catch {
    return false
  }
}

// 将外部链接交给系统浏览器，并限制应用内导航范围。
function wireExternalNavigation(mainWindow, rendererUrl) {
  const rendererOrigin = rendererUrl ? new URL(rendererUrl).origin : null

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (rendererOrigin && hasSameOrigin(url, rendererOrigin)) {
      return { action: 'allow' }
    }

    if (isHttpUrl(url)) {
      void shell.openExternal(url)
    }

    return { action: 'deny' }
  })

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url === mainWindow.webContents.getURL()) {
      return
    }

    if (!rendererOrigin && isHttpUrl(url)) {
      event.preventDefault()
      void shell.openExternal(url)
      return
    }

    if (rendererOrigin && !hasSameOrigin(url, rendererOrigin)) {
      event.preventDefault()
      void shell.openExternal(url)
    }
  })
}

// 创建主窗口，并把后端 URL 注入渲染进程。
async function createWindow(runtimeConfig) {
  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    icon: getAppIconPath(),
    backgroundColor: '#f6efe6',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      // 渲染进程保留浏览器隔离模型，仅通过 preload 暴露必要配置。
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: runtimeConfig.backendUrl
        ? [`--backend-url=${runtimeConfig.backendUrl}`]
        : [],
    },
  })

  wireExternalNavigation(mainWindow, runtimeConfig.rendererUrl)

  if (runtimeConfig.rendererUrl) {
    await loadRenderer(mainWindow, runtimeConfig.rendererUrl)
    return
  }

  const bundledFrontendEntry = getBundledFrontendEntry()
  console.log(`[electron] 正在从 ${bundledFrontendEntry} 加载打包渲染器`)
  await mainWindow.loadFile(bundledFrontendEntry)
}

// 进程退出前清理后端子进程。
app.on('before-quit', () => {
  app.isQuitting = true
  stopBundledBackend()
})

ipcMain.handle(PDF_EXPORT_CHANNEL, async (event, payload) => {
  const parentWindow = BrowserWindow.fromWebContents(event.sender)
  return exportHtmlToPdf(parentWindow, payload)
})

// 应用就绪后初始化运行时配置并打开第一个窗口。
app.whenReady().then(async () => {
  if (process.platform === 'win32') {
    app.setAppUserModelId('com.occreativeassistant.app')
  }

  const runtimeConfig = await resolveRuntimeConfig()
  await createWindow(runtimeConfig)

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow(runtimeConfig)
    }
  })
})

// 在非 macOS 平台上，所有窗口关闭后退出应用。
app.on('window-all-closed', () => {
  stopBundledBackend()

  if (process.platform !== 'darwin') {
    app.quit()
  }
})
