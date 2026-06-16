import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

// 仓库根目录（脚本位于 scripts/，其父目录即项目根目录）。
const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// 后端本地环境变量文件；用于固定打包所用的 Python（如 PYTHON_BIN），无需修改系统环境。
const backendEnvPath = path.join(rootDir, 'backend', '.env')
const backendPromptsPath = path.join(rootDir, 'backend', 'app', 'agents', 'prompts')
const projectVenvPythonPath = path.join(
  rootDir,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)

/**
 * 极简 .env 解析器：仅支持 KEY=VALUE，并忽略空行和 # 注释。
 * 用于从 backend/.env 读取 PYTHON_BIN / OC_BACKEND_PYTHON；行为类似 dotenv，但不额外引入依赖。
 *
 * @param {string} filePath
 * @returns {Record<string, string>}
 */
function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {}
  }

  const values = {}

  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim().replace(/^\uFEFF/, '')

    if (!line || line.startsWith('#') || !line.includes('=')) {
      continue
    }

    const [rawKey, ...rawValueParts] = line.split('=')
    const key = rawKey.trim().replace(/^\uFEFF/, '')
    const value = rawValueParts.join('=').trim().replace(/^['"]|['"]$/g, '')

    if (key) {
      values[key] = value
    }
  }

  return values
}

// 模块加载时读取一次，供 resolvePythonCommand 使用（相对路径按 rootDir 解析）。
const backendEnv = parseEnvFile(backendEnvPath)

/**
 * 给定 conda / venv 等“环境根目录”前缀，返回当前平台下 python 可执行文件的绝对路径。
 *
 * @param {string} prefix 例如 conda 环境目录，或 miniconda 根目录下的 envs/oc
 */
function getPythonExecutable(prefix) {
  return path.join(
    prefix,
    process.platform === 'win32' ? 'python.exe' : 'bin/python',
  )
}

/**
 * 从 PATH 目录推断可能的 conda“安装根目录”（base 所在层级），用于定位 envs/<name>。
 * 启发式规则：识别 .../Library/bin、.../Scripts|bin，或已经包含 envs/<OC_CONDA_ENV|oc> 的路径。
 *
 * @returns {string[]}
 */
function discoverCondaBasesFromPath() {
  const rawPath = process.env.PATH ?? process.env.Path ?? ''
  const candidates = []

  for (const entry of rawPath.split(path.delimiter)) {
    if (!entry) {
      continue
    }

    const normalizedEntry = path.resolve(entry)
    const entryName = path.basename(normalizedEntry).toLowerCase()
    const parentName = path.basename(path.dirname(normalizedEntry)).toLowerCase()

    if (entryName === 'bin' && parentName === 'library') {
      candidates.push(path.dirname(path.dirname(normalizedEntry)))
      continue
    }

    if (entryName === 'scripts' || entryName === 'bin') {
      candidates.push(path.dirname(normalizedEntry))
      continue
    }

    if (fs.existsSync(getPythonExecutable(path.join(normalizedEntry, 'envs', process.env.OC_CONDA_ENV ?? 'oc')))) {
      candidates.push(normalizedEntry)
    }
  }

  return candidates
}

/**
 * 在候选 conda 根目录中查找名为 OC_CONDA_ENV（默认 oc）的环境所对应的 python。
 *
 * @returns {string | null} 找到时返回可执行文件路径，否则返回 null
 */
function resolveNamedCondaPython() {
  const envName = process.env.OC_CONDA_ENV ?? 'oc'
  const baseCandidates = []

  if (process.env.CONDA_EXE) {
    baseCandidates.push(path.resolve(path.dirname(process.env.CONDA_EXE), '..'))
  }

  baseCandidates.push(...discoverCondaBasesFromPath())

  const seen = new Set()

  for (const baseCandidate of baseCandidates) {
    const normalizedBase = path.resolve(baseCandidate)

    if (seen.has(normalizedBase)) {
      continue
    }

    seen.add(normalizedBase)

    const pythonPath = getPythonExecutable(path.join(normalizedBase, 'envs', envName))

    if (fs.existsSync(pythonPath)) {
      return pythonPath
    }
  }

  return null
}

function getBooleanEnv(name) {
  const value = process.env[name]
  return typeof value === 'string' && ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase())
}

function resolvePythonExecutable(command) {
  const result = spawnSync(command, ['-c', 'import sys; print(sys.executable)'], {
    cwd: rootDir,
    encoding: 'utf8',
    shell: false,
  })

  if (result.status === 0) {
    return result.stdout.trim() || command
  }

  return command
}

function isCondaPython(executablePath) {
  const normalizedPath = executablePath.replace(/\\/g, '/').toLowerCase()
  return (
    normalizedPath.includes('/miniconda') ||
    normalizedPath.includes('/anaconda') ||
    normalizedPath.includes('/conda/envs/') ||
    normalizedPath.includes('/envs/oc/')
  )
}

function assertDistributablePython(command) {
  const executablePath = resolvePythonExecutable(command)

  if (!isCondaPython(executablePath)) {
    return executablePath
  }

  if (getBooleanEnv('OC_ALLOW_CONDA_BACKEND_BUILD')) {
    console.warn(
      `[backend-build] 警告：正在使用 Conda Python 打包，发布到其他 Windows 电脑时可能触发 OpenSSL/DLL 兼容问题：${executablePath}`,
    )
    return executablePath
  }

  throw new Error(
    '检测到后端正在使用 Conda Python 打包，这类构建在其他 Windows 电脑上容易出现 ' +
      `"OPENSSL_Uplink ... no OPENSSL_Applink" 崩溃。\n` +
      `当前 Python：${executablePath}\n` +
      '请先创建项目级 venv：python -m venv .venv，然后用 .venv 安装 backend/requirements.txt。\n' +
      '如果你确认要强制使用 Conda，可临时设置 OC_ALLOW_CONDA_BACKEND_BUILD=1。',
  )
}

/**
 * 决定调用 PyInstaller 时使用哪个 Python，优先级从高到低：
 * 1. 进程环境变量 PYTHON_BIN / OC_BACKEND_PYTHON
 * 2. 项目根目录 .venv
 * 3. backend/.env 中同名键（便于本地固定解释器且不提交到 git）
 * 4. 已激活的非 base conda 环境（CONDA_PREFIX）
 * 5. 名为 OC_CONDA_ENV（默认 oc）的 conda 环境
 * 6. 单独的 CONDA_PREFIX（包括 base）
 * 7. 系统 PATH 上的 python.exe / python3
 *
 * 为了稳定打包，建议使用项目根目录的 .venv。
 *
 * @returns {string}
 */
function resolvePythonCommand() {
  if (process.env.PYTHON_BIN) {
    return process.env.PYTHON_BIN
  }

  if (process.env.OC_BACKEND_PYTHON) {
    return process.env.OC_BACKEND_PYTHON
  }

  if (fs.existsSync(projectVenvPythonPath)) {
    return projectVenvPythonPath
  }

  if (backendEnv.PYTHON_BIN) {
    return backendEnv.PYTHON_BIN
  }

  if (backendEnv.OC_BACKEND_PYTHON) {
    return backendEnv.OC_BACKEND_PYTHON
  }

  if (process.env.CONDA_PREFIX && process.env.CONDA_DEFAULT_ENV && process.env.CONDA_DEFAULT_ENV !== 'base') {
    return getPythonExecutable(process.env.CONDA_PREFIX)
  }

  const namedCondaPython = resolveNamedCondaPython()

  if (namedCondaPython) {
    return namedCondaPython
  }

  if (process.env.CONDA_PREFIX) {
    return getPythonExecutable(process.env.CONDA_PREFIX)
  }

  return process.platform === 'win32' ? 'python.exe' : 'python3'
}

/**
 * 在仓库根目录运行子进程；非零退出码会被视为构建失败并 reject。
 *
 * @param {string} command
 * @param {string[]} args
 * @param {string} name 仅用于错误消息
 */
function run(command, args, name) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: rootDir,
      stdio: 'inherit',
      shell: false,
      env: process.env,
    })

    child.on('error', (error) => {
      reject(new Error(`${name} 启动失败：${error.message}`))
    })

    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }

      reject(new Error(`${name} 退出码为 ${code ?? 1}`))
    })
  })
}

const pythonCommand = resolvePythonCommand()
const pythonExecutable = assertDistributablePython(pythonCommand)
console.log(`[backend-build] 使用 Python：${pythonExecutable}`)

const pyinstallerArgs = [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onedir',
  '--name',
  'oc-creative-backend',
  '--distpath',
  'backend/dist',
  '--workpath',
  'backend/build',
  '--specpath',
  'backend',
  // PyInstaller 需要显式包含 uvicorn 的动态导入模块，否则可执行文件启动时会缺少依赖。
  '--hidden-import',
  'uvicorn.logging',
  '--hidden-import',
  'uvicorn.loops.auto',
  '--hidden-import',
  'uvicorn.protocols.http.auto',
  '--hidden-import',
  'uvicorn.protocols.websockets.auto',
  '--hidden-import',
  'uvicorn.lifespan.on',
  // ChromaDB 和 OpenAI SDK 都会在运行时懒加载；这里显式收集，避免打包后向量存储不可用。
  '--collect-all',
  'chromadb',
  '--hidden-import',
  'openai',
  '--hidden-import',
  'tiktoken_ext.openai_public',
]

if (fs.existsSync(backendEnvPath)) {
  pyinstallerArgs.push('--add-data', `${backendEnvPath}${path.delimiter}.`)
}

if (fs.existsSync(backendPromptsPath)) {
  pyinstallerArgs.push(
    '--add-data',
    `${backendPromptsPath}${path.delimiter}${path.join('app', 'agents', 'prompts')}`,
  )
}

pyinstallerArgs.push('backend/serve.py')

// --onedir：生成 oc-creative-backend.exe + _internal，供 Electron extraResources 复制。
await run(
  pythonCommand,
  pyinstallerArgs,
  '后端构建',
)
