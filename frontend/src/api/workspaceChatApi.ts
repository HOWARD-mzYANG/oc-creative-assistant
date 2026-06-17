import { backendBaseUrl } from './http'

/** 工作区底部对话框的 SSE 事件（second_revision 变更 B / W5）。 */
export type WorkspaceChatEvent =
  | { type: 'output'; output_type: 'search' | 'rag' | 'question' | 'feedback'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

/**
 * 工作区被动灵感智能体的 SSE 流。
 *
 * 与 chat 的 streamChat 同构：fetch + ReadableStream 解析；每收到一条完整 data 行就调用一次
 * onEvent。它是被动响应，只有用户发送消息时才产生输出。
 */
export async function streamWorkspaceChat(
  projectId: string,
  message: string,
  quotedNodeIds: string[],
  onEvent: (event: WorkspaceChatEvent) => void,
): Promise<void> {
  const response = await fetch(`${backendBaseUrl}/api/projects/${projectId}/workspace_chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, quoted_node_ids: quotedNodeIds }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`工作区对话请求失败：HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const raw of chunks) {
      const line = raw.trim()
      if (!line.startsWith('data: ')) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as WorkspaceChatEvent)
      } catch {
        /* 跳过损坏的分片。 */
      }
    }
  }
}
