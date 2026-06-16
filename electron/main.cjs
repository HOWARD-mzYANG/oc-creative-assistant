const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron')

// 打包模式下 Electron 主进程托管后端进程；开发模式通常复用外部 uvicorn。
let backendProcess = null
const PDF_EXPORT_CHANNEL = 'oc:export-project-pdf'
const ZOOM_MIN = 0.5
const ZOOM_MAX = 2
const ZOOM_STEP = 0.1

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

// 避免浮点误差累积导致 1.2000000002 这类缩放值。
function clampZoomFactor(value) {
  const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, value))
  return Math.round(clamped * 100) / 100
}

function setWindowZoom(window, factor) {
  if (!window || window.isDestroyed()) {
    return
  }

  window.webContents.setZoomFactor(clampZoomFactor(factor))
}

function adjustWindowZoom(window, delta) {
  if (!window || window.isDestroyed()) {
    return
  }

  setWindowZoom(window, window.webContents.getZoomFactor() + delta)
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

function resolveLogFilePath(fileName) {
  const logDir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  return path.join(logDir, fileName)
}

function formatErrorForLog(error) {
  if (error instanceof Error) {
    return error.stack ?? error.message
  }

  return String(error)
}

function appendStartupLog(message) {
  try {
    const logFilePath = resolveLogFilePath('startup.log')
    fs.appendFileSync(
      logFilePath,
      `${new Date().toISOString()} ${message}\n`,
      'utf8',
    )
    return logFilePath
  } catch (error) {
    console.error('[electron] Failed to write startup log', error)
    return null
  }
}

function createBackendLogSink() {
  let stream = null
  let logFilePath = null

  try {
    logFilePath = resolveLogFilePath('backend.log')
    stream = fs.createWriteStream(logFilePath, { flags: 'a' })
    stream.on('error', (error) => {
      console.error('[electron] Failed to write backend log', error)
    })
    stream.write(`\n${new Date().toISOString()} packaged backend startup\n`)
  } catch (error) {
    console.error('[electron] Failed to create backend log', error)
  }

  return {
    get logFilePath() {
      return logFilePath
    },
    line(message) {
      if (!stream) {
        return
      }

      stream.write(`${new Date().toISOString()} ${message}\n`)
    },
    chunk(prefix, data) {
      if (!stream) {
        return
      }

      const text = Buffer.isBuffer(data) ? data.toString('utf8') : String(data)
      stream.write(`${new Date().toISOString()} ${prefix} ${text}`)
    },
    close() {
      if (!stream) {
        return
      }

      const currentStream = stream
      stream = null
      currentStream.end()
    },
  }
}

function formatBackendExitReason(code, signal) {
  return signal ? `signal ${signal}` : `exit code ${code ?? 0}`
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
  const backendLogSink = createBackendLogSink()

  backendLogSink.line(`executable=${executablePath}`)
  backendLogSink.line(`dataDir=${backendDataDir}`)
  backendLogSink.line(`healthUrl=${backendHealthUrl}`)

  if (!fs.existsSync(executablePath)) {
    backendLogSink.line(`missing executable: ${executablePath}`)
    backendLogSink.close()
    throw new Error(
      `Bundled backend executable was not found at ${executablePath}. ` +
        `Backend log: ${backendLogSink.logFilePath ?? 'unavailable'}`,
    )
  }

  // 如果端口被占用，后端实际端口可能会变化；最终 URL 会通过 preload 注入前端。
  // Electron 显式传入数据目录，避免后端写入便携版构建的临时解压目录。
  backendProcess = spawn(
    executablePath,
    ['--host', backendHost, '--port', String(selectedBackendPort)],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
      env: {
        ...process.env,
        OC_CREATIVE_DATA_DIR: backendDataDir,
      },
    },
  )

  backendProcess.stdout?.on('data', (data) => {
    backendLogSink.chunk('[stdout]', data)
  })

  backendProcess.stderr?.on('data', (data) => {
    backendLogSink.chunk('[stderr]', data)
  })

  let backendReady = false
  const backendExitPromise = new Promise((_, reject) => {
    backendProcess.once('error', (error) => {
      backendLogSink.line(`spawn error: ${formatErrorForLog(error)}`)
      backendLogSink.close()
      backendProcess = null
      reject(
        new Error(
          `Bundled backend failed to start: ${error.message}. ` +
            `Backend log: ${backendLogSink.logFilePath ?? 'unavailable'}`,
        ),
      )
    })

    backendProcess.once('exit', (code, signal) => {
      const reason = formatBackendExitReason(code, signal)
      backendLogSink.line(`backend exited (${reason})`)
      backendLogSink.close()
      backendProcess = null

      if (app.isQuitting) {
        return
      }

      if (backendReady) {
        console.error(`[electron] Packaged backend exited unexpectedly (${reason})`)
        return
      }

      console.error(`[electron] Packaged backend exited before startup (${reason})`)
      reject(
        new Error(
          `Bundled backend exited before it became ready (${reason}). ` +
            `Backend log: ${backendLogSink.logFilePath ?? 'unavailable'}`,
        ),
      )
    })
  })

  try {
    await Promise.race([waitForUrl(backendHealthUrl), backendExitPromise])
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    const backendLogHint = backendLogSink.logFilePath && !errorMessage.includes(backendLogSink.logFilePath)
      ? ` Backend log: ${backendLogSink.logFilePath}`
      : ''
    backendLogSink.line(`backend readiness failed: ${formatErrorForLog(error)}`)
    stopBundledBackend()
    throw new Error(`Bundled backend did not become ready: ${errorMessage}.${backendLogHint}`)
  }

  backendReady = true
  backendLogSink.line('backend health check passed')

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

// 注册窗口级界面缩放快捷键：Ctrl/Cmd + +/-/0。
function wireZoomShortcuts(mainWindow) {
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') {
      return
    }

    const hasCommandModifier = process.platform === 'darwin'
      ? input.meta
      : input.control
    if (!hasCommandModifier || input.alt) {
      return
    }

    const key = String(input.key || '').toLowerCase()
    const code = String(input.code || '')
    if (key === '+' || key === '=' || code === 'Equal' || code === 'NumpadAdd') {
      adjustWindowZoom(mainWindow, ZOOM_STEP)
      event.preventDefault()
      return
    }

    if (key === '-' || key === '_' || code === 'Minus' || code === 'NumpadSubtract') {
      adjustWindowZoom(mainWindow, -ZOOM_STEP)
      event.preventDefault()
      return
    }

    if (key === '0' || code === 'Digit0' || code === 'Numpad0') {
      setWindowZoom(mainWindow, 1)
      event.preventDefault()
    }
  })
}

function installApplicationMenu() {
  const template = [
    ...(process.platform === 'darwin'
      ? [{
          label: app.name,
          submenu: [
            { role: 'about', label: '关于' },
            { type: 'separator' },
            { role: 'hide', label: '隐藏' },
            { role: 'hideOthers', label: '隐藏其他' },
            { role: 'unhide', label: '全部显示' },
            { type: 'separator' },
            { role: 'quit', label: '退出' },
          ],
        }]
      : []),
    {
      label: '编辑',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' },
      ],
    },
    {
      label: '视图',
      submenu: [
        {
          label: '放大',
          accelerator: 'CommandOrControl+=',
          click: (_menuItem, browserWindow) => adjustWindowZoom(browserWindow, ZOOM_STEP),
        },
        {
          label: '缩小',
          accelerator: 'CommandOrControl+-',
          click: (_menuItem, browserWindow) => adjustWindowZoom(browserWindow, -ZOOM_STEP),
        },
        {
          label: '重置缩放',
          accelerator: 'CommandOrControl+0',
          click: (_menuItem, browserWindow) => setWindowZoom(browserWindow, 1),
        },
        { type: 'separator' },
        { role: 'reload', label: '重新加载' },
        { role: 'toggleDevTools', label: '开发者工具' },
      ],
    },
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
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
  wireZoomShortcuts(mainWindow)

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

function showStartupFailure(error) {
  const message = error instanceof Error ? error.message : String(error)
  const logPath = appendStartupLog(`startup failed:\n${formatErrorForLog(error)}`)
  const logHint = logPath ? `\n\nStartup log: ${logPath}` : ''

  dialog.showErrorBox(
    'OC Creative Assistant failed to start',
    `${message}${logHint}`,
  )
  app.quit()
}

async function bootstrapApplication() {
  if (process.platform === 'win32') {
    app.setAppUserModelId('com.occreativeassistant.app')
  }

  installApplicationMenu()

  const runtimeConfig = await resolveRuntimeConfig()
  await createWindow(runtimeConfig)

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      try {
        await createWindow(runtimeConfig)
      } catch (error) {
        showStartupFailure(error)
      }
    }
  })
}

// 应用就绪后初始化运行时配置并打开第一个窗口。
app.whenReady().then(bootstrapApplication).catch(showStartupFailure)

// 在非 macOS 平台上，所有窗口关闭后退出应用。
app.on('window-all-closed', () => {
  stopBundledBackend()

  if (process.platform !== 'darwin') {
    app.quit()
  }
})
