import { spawn } from 'node:child_process'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const nodeCommand = process.execPath

// 运行子命令；一旦失败就中止整个构建流水线。
function run(command, args, name) {
  return new Promise((resolve, reject) => {
    const useShell = process.platform === 'win32' && /\.cmd$/i.test(command)

    const child = spawn(command, args, {
      cwd: rootDir,
      env: process.env,
      stdio: 'inherit',
      shell: useShell,
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

// 依次构建前端、后端、资源目录和最终 Electron 安装包。
await run(npmCommand, ['--prefix', 'frontend', 'run', 'build'], '前端构建')
await run(nodeCommand, ['scripts/build-backend.mjs'], '后端构建')
await run(nodeCommand, ['scripts/prepare-electron-package.mjs'], 'Electron 包资源准备')
await run(npmCommand, ['--prefix', 'electron', 'run', 'build'], 'Electron 构建')
