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

/** Chat + Workspace：自动应用暂存项，并显示行内卡片（编辑 / 丢弃）。 */
function usesAutoApplyStaging(): boolean {
  const path = router.currentRoute.value.path
  return path.startsWith('/workspace/') || path.startsWith('/chat/')
}

/** ChatWorkspace 使用的轻量消息模型（历史消息和本轮流式消息共用）。 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  agentType?: string
  /** 本轮后台自动持久化的卡片（revamp 1：行内显示在聊天中）。 */
  applied?: AppliedEntityDto[]
  /** 网页搜索来源链接（research / 外部事实）。 */
  webSources?: WebSourceDto[]
  /** 相关节点（回复中引用过）。 */
  relatedNodes?: RelatedNodeDto[]
  /** 当前本地轮次的可见推理轨迹；不持久化到历史记录。 */
  trace?: AgentTraceItemDto[]
  /** reasoning 模型返回的原始思考内容；仅当前本地轮次使用。 */
  providerThinking?: string
}

/**
 * 全屏聊天状态仓库（first_revision 第 4 阶段）。
 *
 * 管理会话生命周期、消息流（复用 streamChat SSE）以及后台抽取出的暂存列表。
 * 默认关闭后台抽取；显式画布编辑仍走 structure_agent -> staging -> canvas_apply。
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
  /** 当前轮次仍在流式输出时展示的行内卡片（工作区自动应用）。 */
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

  /** 根据已接受的暂存项重建行内卡片（聊天消息本身不保存这些卡片）。 */
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
      /* 行内卡片只是可选的 UI 增强。 */
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

  /** 进入项目：加载会话列表，复用最近会话（刷新时不自动新建）。 */
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

  /** 从后端重新加载会话列表。 */
  async function loadSessions(): Promise<void> {
    if (!projectId.value) return
    sessions.value = await listProjectSessions(projectId.value)
  }

  /** 切换到指定会话，并加载历史消息和行内卡片。 */
  async function switchSession(id: string): Promise<void> {
    if (!id) return
    sessionId.value = id
    messages.value = (await listSessionMessages(id)).map(_toMessage)
    await hydrateAppliedIntoMessages()
  }

  /** 新建聊天会话并切换过去（仅由用户显式操作触发）。 */
  async function newSession(): Promise<void> {
    if (!projectId.value) return
    const session = await createChatSession(projectId.value, '新对话')
    sessions.value = [session, ...sessions.value]
    sessionId.value = session.id
    messages.value = []
  }

  /** 删除会话；如果删除的是当前会话，则回退到剩余会话中最近的一条（或新建）。 */
  async function deleteSession(id: string): Promise<void> {
    await deleteChatSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (sessionId.value === id) {
      if (sessions.value.length) await switchSession(sessions.value[0].id)
      else await newSession()
    }
  }

  /** 重命名会话并同步本地列表。 */
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

  /** 从服务器重新加载历史消息（每轮结束后的唯一可信来源）。 */
  async function reloadMessages(): Promise<void> {
    if (!sessionId.value) return
    try {
      messages.value = (await listSessionMessages(sessionId.value)).map(_toMessage)
      await hydrateAppliedIntoMessages()
    } catch {
      /* 重新加载失败时保留乐观消息。 */
    }
  }

  /** 发送消息，启用后台流程，并通过流式响应接收回复。 */
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
    // 乐观用户气泡；后端 persistence_hub 也会写入本轮消息。
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
        false, // extraction_enabled：默认关闭后台抽取 / 追问规划，避免回复结束后继续卡住。
        webSearchMode,
        shouldAutoApply,
      )
      // 用服务器持久化后的消息替换本地乐观副本，避免重复。
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
      error.value = e instanceof Error ? e.message : '回复失败'
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
          /* 标题生成是尽力而为的辅助能力。 */
        }
      }
    }
  }

  /** 编辑指定行内卡片背后的节点标题 / 正文（revamp 1）。 */
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

  /** 撤销（删除）指定行内卡片背后的节点（revamp 1：默认新增，可丢弃）。 */
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
