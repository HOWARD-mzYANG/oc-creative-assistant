import { backendBaseUrl, requestJson } from './http'

/** 聊天会话 DTO；thread_id 供 LangGraph Checkpointer 使用。 */
export interface ChatSessionDto {
  id: string
  project_id: string
  thread_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface RelatedNodeDto {
  id: string
  title: string
  node_type: string
}

/** research 回复下方展示的网页搜索来源链接。 */
export interface WebSourceDto {
  title: string
  url: string
  snippet?: string
}

/** 单条聊天消息 DTO；meta 携带 agent_type / cited_node_ids / staging_summary。 */
export interface ChatMessageDto {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  meta: {
    agent_type?: string
    cited_node_ids?: string[]
    staging_summary?: string
    web_sources?: WebSourceDto[]
  }
  created_at: string
}

/** 一轮智能体推理后的聊天回复和暂存摘要。 */
export interface ChatResponseDto {
  message_id: string
  reply_text: string
  cited_node_ids: string[]
  intent: string
  batch_id: string | null
  staging_count: number
  staging_summary: string
}

export interface AgentTraceItemDto {
  node: string
  title: string
  content: string
}

/** 单个暂存项 DTO；与后端暂存 payload 对齐。 */
export interface AgentStagingItemDto {
  id: string
  session_id: string
  message_id: string
  project_id: string
  batch_id: string
  change_type: 'create_node' | 'create_edge' | 'update_node' | 'delete_node' | 'delete_edge'
  target_id: string | null
  pending_id: string | null
  payload: Record<string, unknown>
  payload_edited: Record<string, unknown> | null
  agent_type: string
  reasoning: string
  order_in_batch: number
  status: 'pending' | 'accepted' | 'edited' | 'rejected'
  created_at: string
  resolved_at: string | null
}

/** 暂存批次 DTO；聚合同一 batch_id 下的多项变更用于展示。 */
export interface AgentStagingBatchDto {
  batch_id: string
  items: AgentStagingItemDto[]
}

/**
 * 创建聊天会话；同时分配用于 LangGraph 持久化的 thread_id。
 */
export async function createChatSession(projectId: string, title = ''): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, title }),
  })
}

/** 列出指定项目下的会话，最新创建的排在前面。 */
export async function listProjectSessions(projectId: string): Promise<ChatSessionDto[]> {
  return requestJson<ChatSessionDto[]>(`/api/projects/${projectId}/sessions`)
}

/** 删除聊天会话（messages / staging 在后端级联删除）。 */
export async function deleteChatSession(sessionId: string): Promise<void> {
  await requestJson<void>(`/api/sessions/${sessionId}`, { method: 'DELETE' })
}

/** 重命名聊天会话。 */
export async function renameChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

/** 请求后端把用户第一条消息概括为会话标题。 */
export async function generateSessionTitle(
  sessionId: string,
  userMessage: string,
): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>(`/api/sessions/${sessionId}/title`, {
    method: 'POST',
    body: JSON.stringify({ user_message: userMessage }),
  })
}

/** 读取会话完整消息历史，最旧消息在前。 */
export async function listSessionMessages(sessionId: string): Promise<ChatMessageDto[]> {
  return requestJson<ChatMessageDto[]>(`/api/sessions/${sessionId}/messages`)
}

/**
 * 触发一次完整 agent_graph 推理；返回回复和暂存摘要。
 * 单轮 DeepSeek 调用可能需要几十秒，因此调用方需要自行处理 loading 状态。
 */
export async function postChat(
  sessionId: string,
  userMessage: string,
  selectedNodeIds: string[] = [],
): Promise<ChatResponseDto> {
  return requestJson<ChatResponseDto>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      user_message: userMessage,
      selected_node_ids: selectedNodeIds,
    }),
  })
}

/** 列出当前会话的暂存项，默认只取 pending；后端会按批次自动分组。 */
export async function listSessionStaging(
  sessionId: string,
  status: AgentStagingItemDto['status'] | null = 'pending',
): Promise<AgentStagingBatchDto[]> {
  const query = status ? `?status=${status}` : ''
  return requestJson<AgentStagingBatchDto[]>(`/api/sessions/${sessionId}/staging${query}`)
}

/** 列出整个项目的暂存项（first_revision 第 4 阶段：ChatWorkspace 跨会话审核）。 */
export async function listProjectStaging(
  projectId: string,
  status: AgentStagingItemDto['status'] | null = 'pending',
): Promise<AgentStagingBatchDto[]> {
  const query = status ? `?status=${status}` : ''
  return requestJson<AgentStagingBatchDto[]>(`/api/projects/${projectId}/staging${query}`)
}

/** 接受 / 编辑 / 拒绝单个暂存项；处理已完成项时会返回 409。 */
export async function resolveStagingItem(
  stagingId: string,
  action: 'accept' | 'edit' | 'reject',
  payloadEdited?: Record<string, unknown>,
): Promise<AgentStagingItemDto> {
  return requestJson<AgentStagingItemDto>(`/api/staging/${stagingId}`, {
    method: 'PATCH',
    body: JSON.stringify({ action, payload_edited: payloadEdited ?? null }),
  })
}

/** 批量接受 / 拒绝同一轮的暂存项；已处理项会静默跳过。 */
export async function resolveStagingBatch(
  batchId: string,
  action: 'accept_all' | 'reject_all',
): Promise<AgentStagingItemDto[]> {
  return requestJson<AgentStagingItemDto[]>(`/api/staging/batch/${batchId}`, {
    method: 'PATCH',
    body: JSON.stringify({ action }),
  })
}

/** SSE 事件类型，与后端 chat_stream._sse 的 payload 对齐。 */
export type ChatStreamEvent =
  | { type: 'node_start'; node: string; label: string }
  | { type: 'node_end'; node: string; label: string }
  | { type: 'node_timing'; node: string; label: string; elapsed_ms: number }
  | ({ type: 'trace_item' } & AgentTraceItemDto)
  | { type: 'intent'; primary: string; confidence: number }
  | { type: 'reasoning_token'; text: string }
  | { type: 'reply_token'; text: string }
  | {
      type: 'reply_ready'
      reply_text: string
      cited_node_ids: string[]
      staging_summary: string
      web_sources?: WebSourceDto[]
      related_nodes?: RelatedNodeDto[]
    }
  | {
      type: 'persistence_done'
      message_id: string
      batch_id: string | null
      staging_count: number
    }
  | {
      type: 'extraction_applied'
      items: AppliedEntityDto[]
    }
  | { type: 'done' }
  | {
      type: 'error'
      message: string
      debug?: {
        phase: string
        last_node: string | null
        error_type: string
        error_message: string
        traceback: string
      }
    }

/** 后台抽取并自动持久化的卡片（revamp 1：默认新增，行内显示在聊天中）。 */
export interface AppliedEntityDto {
  node_id: string
  title: string
  node_type: string
  content: string
  change_type: 'create_node' | 'update_node'
}

/**
 * 流式聊天：后端 SSE，前端 fetch + ReadableStream 解析。
 *
 * EventSource 不支持 POST + body，因此这里使用原生 fetch。每收到一条完整 SSE data 行就调用一次
 * onEvent，让组件渐进式更新 UI。
 */
export type WebSearchMode = 'auto' | 'on' | 'off'

/** 调用后端接口，执行 streamChat 对应的请求。 */
export async function streamChat(
  sessionId: string,
  userMessage: string,
  selectedNodeIds: string[],
  onEvent: (event: ChatStreamEvent) => void,
  extractionEnabled = false,
  webSearchMode: WebSearchMode = 'auto',
  autoApplyStaging = false,
): Promise<void> {
  const response = await fetch(`${backendBaseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      user_message: userMessage,
      selected_node_ids: selectedNodeIds,
      extraction_enabled: extractionEnabled,
      auto_apply_staging: autoApplyStaging,
      web_search_mode: webSearchMode,
    }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`流式聊天请求失败：HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    /* SSE 协议中事件以 \n\n 分隔；不完整片段会留在 buffer 中等待下一帧。 */
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const raw of chunks) {
      const line = raw.trim()
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6)) as ChatStreamEvent
        onEvent(data)
      } catch {
        /* 跳过损坏片段，保持流继续。 */
      }
    }
  }
}

/** 后端健康检查响应；boot_id 用于检测后端进程是否重启。 */
export interface HealthDto {
  status: string
  service: string
  boot_id: string
}

/**
 * 获取后端 boot_id；失败时返回空字符串，表示“无法识别”，由调用方决定兜底策略。
 */
export async function fetchBackendBootId(): Promise<string> {
  try {
    const data = await requestJson<HealthDto>('/health')
    return data.boot_id ?? ''
  } catch {
    return ''
  }
}

export { backendBaseUrl }
