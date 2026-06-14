import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const bundleDir = path.join(rootDir, 'electron', '.bundle')
const frontendDistDir = path.join(rootDir, 'frontend', 'dist')
const backendDistDir = path.join(rootDir, 'backend', 'dist', 'oc-creative-backend')

// 缺少必要构建产物时尽早失败。
function ensureExists(targetPath, label) {
  if (!fs.existsSync(targetPath)) {
    throw new Error(`${label} 未在 ${targetPath} 找到`)
  }
}

// 先确认前端和后端构建产物都存在。
ensureExists(frontendDistDir, '前端构建输出')
ensureExists(backendDistDir, '后端构建输出')

// 重新创建临时 Electron 打包目录。
// 该目录是构建产物，可以安全清理；不要把用户数据放在 electron/.bundle 下。
fs.rmSync(bundleDir, { recursive: true, force: true })
fs.mkdirSync(bundleDir, { recursive: true })

// 将前端和后端产物复制到 Electron 资源目录。
fs.cpSync(frontendDistDir, path.join(bundleDir, 'frontend'), { recursive: true })
fs.cpSync(backendDistDir, path.join(bundleDir, 'backend'), { recursive: true })
