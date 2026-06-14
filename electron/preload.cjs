const { contextBridge, ipcRenderer } = require('electron')

const PDF_EXPORT_CHANNEL = 'oc:export-project-pdf'

// 读取主进程通过 additionalArguments 传入的单个参数。
function readAdditionalArgument(name) {
  const prefix = `--${name}=`
  const entry = process.argv.find((argument) => argument.startsWith(prefix))

  if (!entry) {
    return null
  }

  return entry.slice(prefix.length)
}

// 只向渲染进程暴露必要的最小运行时信息。
// 注意：不要在这里暴露任意 Node/Electron API，以免扩大前端攻击面。
contextBridge.exposeInMainWorld('ocDesktop', {
  config: {
    backendUrl: readAdditionalArgument('backend-url') ?? process.env.BACKEND_BASE_URL ?? null,
  },
  runtime: {
    platform: process.platform,
    versions: {
      chrome: process.versions.chrome,
      electron: process.versions.electron,
      node: process.versions.node,
    },
  },
  exportProjectPdf: (payload) => ipcRenderer.invoke(PDF_EXPORT_CHANNEL, payload),
})
