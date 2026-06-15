import { backendBaseUrl, requestJson } from './http'

/** Chat session DTO; thread_id is used by the LangGraph Checkpointer. */
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

/** Web search source link shown under research replies. */
export interface WebSourceDto {
  title: string
  url: string
  snippet?: string
}

/** Single chat message DTO; meta carries agent_type / cited_node_ids / staging_summary. */
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

/** Chat reply after one Agent reasoning turn + staging summary. */
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

/** Single staging item DTO; aligned with the backend AgentStagingPayload. */
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

/** Staging batch DTO; aggregates multiple changes that share a batch_id for display. */
export interface AgentStagingBatchDto {
  batch_id: string
  items: AgentStagingItemDto[]
}

/**
 * Create a chat session; also assigns a thread_id for LangGraph persistence.
 */
export async function createChatSession(projectId: string, title = ''): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, title }),
  })
}

/** List the sessions under a given project, newest created first. */
export async function listProjectSessions(projectId: string): Promise<ChatSessionDto[]> {
  return requestJson<ChatSessionDto[]>(`/api/projects/${projectId}/sessions`)
}

/** Delete a chat session (messages / staging cascade on the backend). */
export async function deleteChatSession(sessionId: string): Promise<void> {
  await requestJson<void>(`/api/sessions/${sessionId}`, { method: 'DELETE' })
}

/** Rename a chat session. */
export async function renameChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

/** Ask the backend to summarize the first user message into a session title. */
export async function generateSessionTitle(
  sessionId: string,
  userMessage: string,
): Promise<ChatSessionDto> {
  return requestJson<ChatSessionDto>(`/api/sessions/${sessionId}/title`, {
    method: 'POST',
    body: JSON.stringify({ user_message: userMessage }),
  })
}

/** Read the full message history of a session, oldest first. */
export async function listSessionMessages(sessionId: string): Promise<ChatMessageDto[]> {
  return requestJson<ChatMessageDto[]>(`/api/sessions/${sessionId}/messages`)
}

/**
 * Trigger a full agent_graph reasoning pass; returns the reply + staging summary.
 * A single DeepSeek turn may take tens of seconds, so the caller should handle the loading state itself.
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

/** List the staging of the current session, pending only by default; auto-grouped by batch. */
export async function listSessionStaging(
  sessionId: string,
  status: AgentStagingItemDto['status'] | null = 'pending',
): Promise<AgentStagingBatchDto[]> {
  const query = status ? `?status=${status}` : ''
  return requestJson<AgentStagingBatchDto[]>(`/api/sessions/${sessionId}/staging${query}`)
}

/** List the staging of the whole project (first_revision phase 4: ChatWorkspace cross-session review). */
export async function listProjectStaging(
  projectId: string,
  status: AgentStagingItemDto['status'] | null = 'pending',
): Promise<AgentStagingBatchDto[]> {
  const query = status ? `?status=${status}` : ''
  return requestJson<AgentStagingBatchDto[]>(`/api/projects/${projectId}/staging${query}`)
}

/** Accept / edit / reject a single staging item; acting on an already-resolved item returns 409. */
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

/** Bulk accept / reject the staging of the same turn; already-resolved items are silently skipped. */
export async function resolveStagingBatch(
  batchId: string,
  action: 'accept_all' | 'reject_all',
): Promise<AgentStagingItemDto[]> {
  return requestJson<AgentStagingItemDto[]>(`/api/staging/batch/${batchId}`, {
    method: 'PATCH',
    body: JSON.stringify({ action }),
  })
}

/** SSE event types, aligned with the payload of the backend chat_stream._sse. */
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

/** A card extracted in the background and [auto-persisted] (revamp 1: inline display in chat, added by default). */
export interface AppliedEntityDto {
  node_id: string
  title: string
  node_type: string
  content: string
  change_type: 'create_node' | 'update_node'
}

/**
 * Streaming chat: backend SSE, frontend fetch + ReadableStream parsing.
 *
 * EventSource does not support POST + body, so we use native fetch. onEvent is
 * called once for each complete SSE data line, letting the component update the UI progressively.
 */
export type WebSearchMode = 'auto' | 'on' | 'off'

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
    throw new Error(`stream failed: HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    /* SSE protocol: events are separated by \n\n; an incomplete one stays in the buffer for the next frame */
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const raw of chunks) {
      const line = raw.trim()
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6)) as ChatStreamEvent
        onEvent(data)
      } catch {
        /* skip the corrupted chunk and keep the stream going */
      }
    }
  }
}

/** Backend health-check response; boot_id is used to detect whether the backend process has been restarted. */
export interface HealthDto {
  status: string
  service: string
  boot_id: string
}

/**
 * Fetch the backend boot_id; on failure returns an empty string meaning "unidentifiable"; the caller decides the fallback strategy.
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
