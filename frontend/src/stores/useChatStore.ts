import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  AgentTraceItemDto,
  AgentStagingItemDto,
  AppliedEntityDto,
  ChatMessageDto,
  ChatSessionDto,
  RelatedNodeDto,
  WebSearchMode,
  WebSourceDto,
} from '../api/chatApi'
import {
  createChatSession,
  deleteChatSession,
  generateSessionTitle,
  listProjectSessions,
  listSessionMessages,
  listSessionStaging,
  renameChatSession,
  streamChat,
} from '../api/chatApi'
import { deleteNode as apiDeleteNode, updateNode as apiUpdateNode } from '../api/projectApi'
import { router } from '../router'

/** Chat + workspace: auto-apply staging, show ✅ inline cards (edit / discard). */
function usesAutoApplyStaging(): boolean {
  const path = router.currentRoute.value.path
  return path.startsWith('/workspace/') || path.startsWith('/chat/')
}

/** The lightweight message model used in ChatWorkspace (shared by historical messages + this turn's streaming message). */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  agentType?: string
  /** Cards auto-persisted in the background this turn (revamp 1: inline display in chat). */
  applied?: AppliedEntityDto[]
  /** Web search source links (research / external facts). */
  webSources?: WebSourceDto[]
  /** Related nodes (cited in the reply). */
  relatedNodes?: RelatedNodeDto[]
  /** Visible reasoning trace for the current local turn; not persisted in history. */
  trace?: AgentTraceItemDto[]
  /** Raw provider thinking returned by reasoning models; current local turn only. */
  providerThinking?: string
}

/**
 * Full-screen chat store (first_revision phase 4).
 *
 * Handles the session lifecycle, message stream (reusing streamChat SSE), and the staging list extracted in the background.
 * Keeps background extraction off by default; explicit canvas edits still go through
 * structure_agent -> staging -> canvas_apply.
 */
export const useChatStore = defineStore('chat', () => {
  const projectId = ref('')
  const sessionId = ref('')
  const sessions = ref<ChatSessionDto[]>([])
  const messages = ref<ChatMessage[]>([])
  const streamingReply = ref('')
  const streamingWebSources = ref<WebSourceDto[]>([])
  const streamingTrace = ref<AgentTraceItemDto[]>([])
  const streamingProviderThinking = ref('')
  /** Inline ✅ cards while the current turn is still streaming (workspace auto-apply). */
  const streamingApplied = ref<AppliedEntityDto[]>([])
  const isStreaming = ref(false)
  const progressLabel = ref('')
  const lastAgent = ref('')
  const error = ref('')

  function _stagingItemToApplied(item: AgentStagingItemDto): AppliedEntityDto | null {
    if (item.change_type !== 'create_node' && item.change_type !== 'update_node') return null
    if (!item.target_id) return null
    if (item.status !== 'accepted' && item.status !== 'edited') return null
    const payload = { ...item.payload, ...(item.payload_edited ?? {}) }
    const fallbackTitle = item.change_type === 'update_node' ? '已更新节点' : '未命名'
    return {
      node_id: item.target_id,
      title: String(payload.title ?? fallbackTitle),
      node_type: String(payload.node_type ?? 'node'),
      content: String(payload.content ?? ''),
      change_type: item.change_type,
    }
  }

  function _pushApplied(target: AppliedEntityDto[], item: AppliedEntityDto) {
    if (!target.some((a) => a.node_id === item.node_id)) target.push(item)
  }

  /** Rebuild ✅ inline cards from accepted staging (not stored on chat messages). */
  async function hydrateAppliedIntoMessages(): Promise<void> {
    if (!sessionId.value || !usesAutoApplyStaging()) return
    try {
      const batches = await listSessionStaging(sessionId.value, null)
      const byMessage = new Map<string, AppliedEntityDto[]>()
      for (const batch of batches) {
        for (const item of batch.items) {
          const applied = _stagingItemToApplied(item)
          if (!applied) continue
          const list = byMessage.get(item.message_id) ?? []
          _pushApplied(list, applied)
          byMessage.set(item.message_id, list)
        }
      }
      for (const message of messages.value) {
        const applied = byMessage.get(message.id)
        if (applied?.length) message.applied = applied
      }
    } catch {
      /* inline cards are optional UI sugar */
    }
  }

  function _toMessage(dto: ChatMessageDto): ChatMessage {
    return {
      id: dto.id,
      role: dto.role,
      content: dto.content,
      agentType: dto.meta?.agent_type,
      webSources: dto.meta?.web_sources?.length ? dto.meta.web_sources : undefined,
    }
  }

  /** Enter a project: load the session list, reuse the most recent one (don't auto-create on refresh). */
  async function init(targetProjectId: string): Promise<void> {
    if (projectId.value === targetProjectId && sessionId.value) {
      await hydrateAppliedIntoMessages()
      return
    }
    projectId.value = targetProjectId
    error.value = ''
    try {
      sessions.value = await listProjectSessions(targetProjectId)
      const session = sessions.value[0] ?? (await createChatSession(targetProjectId, '新对话'))
      if (!sessions.value.length) sessions.value = [session]
      await switchSession(session.id)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '对话启动失败'
    }
  }

  /** Reload the session list from the backend. */
  async function loadSessions(): Promise<void> {
    if (!projectId.value) return
    sessions.value = await listProjectSessions(projectId.value)
  }

  /** Switch to a session and load its history + inline ✅ cards. */
  async function switchSession(id: string): Promise<void> {
    if (!id) return
    sessionId.value = id
    messages.value = (await listSessionMessages(id)).map(_toMessage)
    await hydrateAppliedIntoMessages()
  }

  /** Create a fresh chat session and switch to it (explicit user action only). */
  async function newSession(): Promise<void> {
    if (!projectId.value) return
    const session = await createChatSession(projectId.value, '新对话')
    sessions.value = [session, ...sessions.value]
    sessionId.value = session.id
    messages.value = []
  }

  /** Delete a session; if it was the active one, fall back to the most recent remaining (or a new one). */
  async function deleteSession(id: string): Promise<void> {
    await deleteChatSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (sessionId.value === id) {
      if (sessions.value.length) await switchSession(sessions.value[0].id)
      else await newSession()
    }
  }

  /** Rename a session and sync the local list. */
  async function renameSession(id: string, title: string): Promise<void> {
    const updated = await renameChatSession(id, title)
    sessions.value = sessions.value.map((s) => (s.id === id ? updated : s))
  }

  let onGraphMutated: (() => void | Promise<void>) | null = null

  function setGraphMutatedHandler(handler: (() => void | Promise<void>) | null) {
    onGraphMutated = handler
  }

  async function notifyGraphMutated() {
    if (onGraphMutated) await onGraphMutated()
  }

  /** Reload history from the server (single source of truth after each turn). */
  async function reloadMessages(): Promise<void> {
    if (!sessionId.value) return
    try {
      messages.value = (await listSessionMessages(sessionId.value)).map(_toMessage)
      await hydrateAppliedIntoMessages()
    } catch {
      /* keep optimistic messages if reload fails */
    }
  }

  /** Send a message, enable background extraction, and receive the reply via streaming. */
  async function send(
    text: string,
    selectedNodeIds: string[] = [],
    webSearchMode: WebSearchMode = 'auto',
  ): Promise<void> {
    const content = text.trim()
    if (!content || !sessionId.value || isStreaming.value) return

    const isFirstTurn = messages.value.length === 0
    const turnSessionId = sessionId.value
    isStreaming.value = true
    // Optimistic user bubble; backend persistence_hub also writes this turn.
    messages.value.push({ id: `local-${Date.now()}`, role: 'user', content })
    streamingReply.value = ''
    streamingWebSources.value = []
    streamingTrace.value = []
    streamingProviderThinking.value = ''
    streamingApplied.value = []
    progressLabel.value = '思考中…'
    error.value = ''
    const appliedThisTurn: AppliedEntityDto[] = []
    let relatedThisTurn: RelatedNodeDto[] = []
    let stagingApplied = false
    const shouldAutoApply = usesAutoApplyStaging()
    let graphRefreshRequested = false
    let graphRefreshQueued = false
    let graphRefreshPromise: Promise<void> | null = null

    function queueGraphRefresh() {
      if (!shouldAutoApply) return
      graphRefreshRequested = true
      if (graphRefreshPromise) {
        graphRefreshQueued = true
        return
      }

      const run = async (): Promise<void> => {
        do {
          graphRefreshQueued = false
          await notifyGraphMutated()
        } while (graphRefreshQueued)
      }

      graphRefreshPromise = run().finally(() => {
        graphRefreshPromise = null
      })
    }

    async function drainGraphRefresh() {
      while (graphRefreshPromise) {
        await graphRefreshPromise
      }
    }

    try {
      await streamChat(
        sessionId.value,
        content,
        selectedNodeIds,
        (event) => {
          if (event.type === 'reply_token') {
            streamingReply.value += event.text
          } else if (event.type === 'reasoning_token') {
            streamingProviderThinking.value += event.text
          } else if (event.type === 'node_start') {
            progressLabel.value = event.label
          } else if (event.type === 'node_end') {
            progressLabel.value = event.label
          } else if (event.type === 'node_timing') {
            console.debug(`[agent-timing] ${event.node} ${event.elapsed_ms}ms`)
          } else if (event.type === 'trace_item') {
            streamingTrace.value.push({
              node: event.node,
              title: event.title,
              content: event.content,
            })
          } else if (event.type === 'intent') {
            lastAgent.value = event.primary
          } else if (event.type === 'reply_ready') {
            streamingReply.value = event.reply_text
            streamingWebSources.value = event.web_sources?.length ? [...event.web_sources] : []
            relatedThisTurn = event.related_nodes?.length ? [...event.related_nodes] : []
          } else if (event.type === 'extraction_applied') {
            for (const item of event.items) {
              _pushApplied(appliedThisTurn, item)
              _pushApplied(streamingApplied.value, item)
            }
            if (event.items.length > 0) queueGraphRefresh()
          } else if (event.type === 'persistence_done') {
            if (event.staging_count > 0) {
              stagingApplied = true
              queueGraphRefresh()
            }
          } else if (event.type === 'error') {
            const parts = [event.message]
            if (event.debug?.traceback) {
              parts.push(event.debug.traceback)
            }
            error.value = parts.join('\n\n')
          }
        },
        false, // extraction_enabled：默认关闭后台抽取/追问规划，避免回复结束后继续卡住。
        webSearchMode,
        shouldAutoApply,
      )
      // Replace optimistic local copies with server-persisted messages (avoids duplicates).
      const traceThisTurn = [...streamingTrace.value]
      const providerThinkingThisTurn = streamingProviderThinking.value
      await reloadMessages()
      const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
      if (lastAssistant) {
        const applied =
          appliedThisTurn.length ? appliedThisTurn : lastAssistant.applied?.length ? lastAssistant.applied : streamingApplied.value
        if (applied.length) lastAssistant.applied = [...applied]
        if (relatedThisTurn.length) lastAssistant.relatedNodes = [...relatedThisTurn]
        if (traceThisTurn.length) lastAssistant.trace = traceThisTurn
        if (providerThinkingThisTurn) lastAssistant.providerThinking = providerThinkingThisTurn
        if (!lastAssistant.agentType && lastAgent.value) {
          lastAssistant.agentType = lastAgent.value
        }
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Reply failed'
    } finally {
      streamingReply.value = ''
      streamingWebSources.value = []
      streamingTrace.value = []
      streamingProviderThinking.value = ''
      streamingApplied.value = []
      progressLabel.value = ''
      isStreaming.value = false
      await drainGraphRefresh()
      if (shouldAutoApply && (appliedThisTurn.length || stagingApplied)) {
        if (!graphRefreshRequested) await notifyGraphMutated()
      }
      if (isFirstTurn) {
        try {
          const updated = await generateSessionTitle(turnSessionId, content)
          sessions.value = sessions.value.map((s) => (s.id === updated.id ? updated : s))
        } catch {
          /* title generation is best-effort */
        }
      }
    }
  }

  /** 编辑 the title/body of the node behind a given inline card (revamp 1). */
  async function editAppliedNode(
    nodeId: string,
    patch: { title?: string; content?: string },
  ): Promise<void> {
    if (!projectId.value) return
    await apiUpdateNode(projectId.value, nodeId, patch)
    for (const message of messages.value) {
      const item = message.applied?.find((a) => a.node_id === nodeId)
      if (item) {
        if (patch.title !== undefined) item.title = patch.title
        if (patch.content !== undefined) item.content = patch.content
      }
    }
  }

  /** Undo (delete) the node behind a given inline card (revamp 1: added by default, can be rejected). */
  async function removeAppliedNode(nodeId: string): Promise<void> {
    if (!projectId.value) return
    await apiDeleteNode(projectId.value, nodeId)
    for (const message of messages.value) {
      if (message.applied) {
        message.applied = message.applied.filter((a) => a.node_id !== nodeId)
      }
    }
    await notifyGraphMutated()
  }

  return {
    projectId,
    sessionId,
    sessions,
    messages,
    streamingReply,
    streamingWebSources,
    streamingTrace,
    streamingProviderThinking,
    streamingApplied,
    isStreaming,
    progressLabel,
    lastAgent,
    error,
    init,
    loadSessions,
    switchSession,
    newSession,
    deleteSession,
    renameSession,
    send,
    setGraphMutatedHandler,
    editAppliedNode,
    removeAppliedNode,
  }
})
