/* 桌面模式优先使用 preload 注入的后端地址；浏览器开发模式回退到 Vite 环境变量。 */
export const backendBaseUrl = (
  window.ocDesktop?.config.backendUrl ||
  import.meta.env.VITE_BACKEND_URL ||
  'http://127.0.0.1:9000'
).replace(/\/$/, '')

/**
 * 请求后端 JSON 端点的统一辅助函数。
 *
 * 参数：
 *   path: 以 `/api` 开头的后端路径。
 *   init: fetch 请求配置。
 *
 * 返回：
 *   反序列化后的响应体。
 *
 * 抛出：
 *   错误：后端返回非 2xx 状态时抛出。
 */
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendBaseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  // 204 No Content（例如 DELETE）没有响应体，直接解析 JSON 会抛错。
  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
