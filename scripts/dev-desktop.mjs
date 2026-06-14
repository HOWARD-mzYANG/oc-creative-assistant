import { spawn } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// 标准化端口输入；无效时回退到默认值。
function resolvePort(rawPort, fallback) {
  const parsedPort = Number(rawPort)

  if (Number.isInteger(parsedPort) && parsedPort > 0) {
    return parsedPort
  }

  return fallback
}

const frontendHost = process.env.FRONTEND_DEV_HOST ?? '127.0.0.1'
const frontendPort = resolvePort(process.env.FRONTEND_DEV_PORT, 5174)
const backendHost = process.env.BACKEND_HOST ?? '127.0.0.1'
const backendPort = resolvePort(process.env.BACKEND_PORT, 9000)
const backendReload = process.env.BACKEND_RELOAD !== 'false'
const backendUrlOverride = process.env.VITE_BACKEND_URL?.replace(/\/$/, '') ?? null
const rendererUrlOverride = process.env.ELECTRON_RENDERER_URL?.replace(/\/$/, '') ?? null
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const pythonCommand = process.env.PYTHON_BIN ?? 'python'

const children = []
let isShuttingDown = false

// 使用统一的桌面启动器日志前缀，方便排查问题。
function log(message) {
  console.log(`[desktop] ${message}`)
}

// 根据主机和端口构建本地 HTTP 基础 URL。
function buildHttpUrl(host, port) {
  return `http://${host}:${port}`
}

// 根据基础 URL 构建后端健康检查端点 URL。
function buildHealthUrl(baseUrl) {
  return `${baseUrl.replace(/\/$/, '')}/health`
}

// 启动子进程，并统一注册生命周期处理。
function spawnProcess(name, command, args, extraEnv = {}) {
  log(`正在启动 ${name}...`)
  // 在 Windows 上，npm.cmd 需要 shell 才能正确解析；其他命令直接启动。
  const useShell = process.platform === 'win32' && command.toLowerCase().endsWith('.cmd')

  const child = spawn(command, args, {
    cwd: rootDir,
    env: {
      ...process.env,
      ...extraEnv,
    },
    stdio: 'inherit',
    shell: useShell,
  })

  children.push({ child, name })

  child.on('error', (error) => {
    if (isShuttingDown) {
      return
    }

    console.error(`[desktop] 启动 ${name} 失败：`, error)
    void shutdown(1)
  })

  child.on('exit', (code, signal) => {
    if (isShuttingDown) {
      return
    }

    const reason = signal ? `信号 ${signal}` : `退出码 ${code ?? 0}`

    if (name === 'electron') {
      log(`Electron 已退出（${reason}）。正在关闭其余进程。`)
      void shutdown(code ?? 0)
      return
    }

    console.error(`[desktop] ${name} 提前退出（${reason}）。`)
    void shutdown(code ?? 1)
  })

  return child
}

// 轮询直到指定 HTTP URL 可访问。
async function waitForUrl(url, timeoutMs = 60_000, intervalMs = 500) {
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url)

      if (response.ok) {
        return
      }
    } catch {
      // 持续轮询，直到开发服务器就绪或超时。
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }

  throw new Error(`等待 ${url} 超时`)
}

// 判断是否已有可复用的 Vite 开发服务器在运行。
async function isFrontendReady(baseUrl) {
  try {
    const response = await fetch(new URL('/__vite_ping', `${baseUrl}/`))
    return response.ok
  } catch {
    return false
  }
}

// 判断是否已有可复用的 FastAPI 后端服务在运行。
async function isBackendReady(healthUrl) {
  try {
    const response = await fetch(healthUrl)

    if (!response.ok) {
      return false
    }

    const payload = await response.json()
    return payload?.status === 'ok' && payload?.service === 'backend'
  } catch {
    return false
  }
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

// 从配置的 URL 提取端口；缺失时回退到默认端口。
function readPortFromUrl(url, fallbackPort) {
  try {
    const parsedUrl = new URL(url)

    if (parsedUrl.port) {
      return Number(parsedUrl.port)
    }

    return fallbackPort
  } catch {
    return fallbackPort
  }
}

// 考虑平台差异，安全终止子进程。
function terminateChild(child) {
  if (!child.pid) {
    return
  }

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' })
    return
  }

  child.kill('SIGTERM')
}

// 按启动顺序的反序关闭整个桌面开发进程组。
async function shutdown(exitCode = 0) {
  if (isShuttingDown) {
    return
  }

  isShuttingDown = true

  for (const { child } of [...children].reverse()) {
    terminateChild(child)
  }

  setTimeout(() => {
    process.exit(exitCode)
  }, 200)
}

// 编排本地开发中的前端、后端和 Electron 启动流程。
async function main() {
  let selectedBackendPort = backendPort
  let selectedBackendUrl = backendUrlOverride ?? buildHttpUrl(backendHost, selectedBackendPort)
  let selectedBackendHealthUrl = buildHealthUrl(selectedBackendUrl)
  let shouldStartBackend = false

  const backendRunning = await isBackendReady(selectedBackendHealthUrl)

  if (backendRunning) {
    // 如果后端已可用，直接复用，避免再次启动造成端口冲突或数据文件竞争。
    log(`正在复用已有后端：${selectedBackendHealthUrl}。`)
  } else if (backendUrlOverride) {
    throw new Error(
      `配置的后端 URL ${selectedBackendHealthUrl} 不可访问。请手动启动它，或移除 VITE_BACKEND_URL。`,
    )
  } else {
    selectedBackendPort = await findAvailablePort(backendHost, backendPort)
    selectedBackendUrl = buildHttpUrl(backendHost, selectedBackendPort)
    selectedBackendHealthUrl = buildHealthUrl(selectedBackendUrl)
    shouldStartBackend = true

    if (selectedBackendPort !== backendPort) {
      log(`后端端口 ${backendPort} 不可用，回退到 ${selectedBackendPort}。`)
    }
  }

  let selectedRendererUrl = rendererUrlOverride ?? buildHttpUrl(frontendHost, frontendPort)
  let selectedFrontendPort = readPortFromUrl(selectedRendererUrl, frontendPort)
  let shouldStartFrontend = false

  const frontendRunning = await isFrontendReady(selectedRendererUrl)

  if (frontendRunning) {
    // 复用正在运行的 Vite 实例，可以保留开发者当前页面状态和 HMR 会话。
    log(`正在复用已有前端：${selectedRendererUrl}。`)
  } else if (rendererUrlOverride) {
    throw new Error(
      `配置的渲染器 URL ${selectedRendererUrl} 不可访问。请手动启动它，或移除 ELECTRON_RENDERER_URL。`,
    )
  } else {
    selectedFrontendPort = await findAvailablePort(frontendHost, frontendPort)
    selectedRendererUrl = buildHttpUrl(frontendHost, selectedFrontendPort)
    shouldStartFrontend = true

    if (selectedFrontendPort !== frontendPort) {
      log(`前端端口 ${frontendPort} 不可用，回退到 ${selectedFrontendPort}。`)
    }
  }

  if (shouldStartFrontend) {
    spawnProcess(
      'frontend',
      npmCommand,
      ['--prefix', 'frontend', 'run', 'dev', '--', '--configLoader', 'native'],
      {
        FRONTEND_DEV_HOST: frontendHost,
        FRONTEND_DEV_PORT: String(selectedFrontendPort),
        VITE_BACKEND_URL: selectedBackendUrl,
      },
    )
  }

  const backendArgs = [
    '-m',
    'uvicorn',
    'app.main:app',
    '--host',
    backendHost,
    '--port',
    String(selectedBackendPort),
    '--app-dir',
    'backend',
  ]

  if (backendReload) {
    backendArgs.splice(3, 0, '--reload')
  }

  if (shouldStartBackend) {
    spawnProcess('backend', pythonCommand, backendArgs)
  }

  if (shouldStartFrontend) {
    log(`正在等待前端开发服务器：${selectedRendererUrl}...`)
    await waitForUrl(selectedRendererUrl)
  }

  if (shouldStartBackend) {
    log(`正在等待后端健康检查端点：${selectedBackendHealthUrl}...`)
    await waitForUrl(selectedBackendHealthUrl)
  }

  log('桌面端依赖已就绪，正在启动 Electron。')

  spawnProcess('electron', npmCommand, ['--prefix', 'electron', 'run', 'dev'], {
    BACKEND_BASE_URL: selectedBackendUrl,
    ELECTRON_RENDERER_URL: selectedRendererUrl,
    FRONTEND_DEV_HOST: frontendHost,
    FRONTEND_DEV_PORT: String(selectedFrontendPort),
  })
}

// 收到终止信号时，统一关闭所有子进程。
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    void shutdown(0)
  })
}

// 将未处理的 Promise rejection 接入关闭流程。
process.on('unhandledRejection', (error) => {
  console.error('[desktop] 未处理的 rejection：', error)
  void shutdown(1)
})

// 将未捕获异常接入关闭流程。
process.on('uncaughtException', (error) => {
  console.error('[desktop] 未捕获异常：', error)
  void shutdown(1)
})

// 启动桌面端开发编排器，并清晰报告启动错误。
main().catch((error) => {
  console.error('[desktop] 启动桌面端开发流程失败：', error)
  void shutdown(1)
})
