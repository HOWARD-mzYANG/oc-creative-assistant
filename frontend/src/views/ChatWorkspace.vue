<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../stores/useChatStore'
import { useProjectStore } from '../stores/useProjectStore'
import { rebuildProjectSeed } from '../api/projectApi'
import ChatSessionSidebar from '../components/chat/ChatSessionSidebar.vue'
import AgentTracePanel from '../components/chat/AgentTracePanel.vue'
import InlineEntityCard from '../components/chat/InlineEntityCard.vue'
import ProviderThinkingPanel from '../components/chat/ProviderThinkingPanel.vue'
import WebSourceCard from '../components/chat/WebSourceCard.vue'

marked.use({ gfm: true, breaks: true })

function renderMarkdown(text: string): string {
  return marked.parse(text) as string
}

/**
 * 独立对话模块：项目范围会话 + 主 LangGraph Agent。
 * 后台抽取/暂存与工作区外壳使用相同 API。
 */
const props = defineProps<{ projectId: string }>()
const router = useRouter()

const chat = useChatStore()
const projectStore = useProjectStore()
const {
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
} = storeToRefs(chat)
const { detail } = storeToRefs(projectStore)

const draft = ref('')
const streamRef = ref<HTMLElement | null>(null)

const projectName = computed(() => detail.value?.name ?? '对话')
const hasContent = computed(() => Boolean(draft.value.trim()))

const AGENT_LABELS: Record<string, string> = {
  inspiration: '灵感',
  research: '资料',
  structure: '结构',
  simulation: '模拟',
  small_talk: '对话',
}

onMounted(() => {
  void projectStore.loadProject(props.projectId)
  void chat.init(props.projectId)
})

watch(
  () => props.projectId,
  (id) => {
    void projectStore.loadProject(id)
    void chat.init(id)
  },
)

async function scrollToBottom() {
  await nextTick()
  if (streamRef.value) streamRef.value.scrollTop = streamRef.value.scrollHeight
}

watch(
  [messages, streamingReply, streamingTrace, streamingProviderThinking, streamingApplied],
  scrollToBottom,
  { deep: true },
)

async function handleSend() {
  const text = draft.value.trim()
  if (!text || isStreaming.value) return
  draft.value = ''
  await chat.send(text)
}

async function handleExit() {
  try {
    await rebuildProjectSeed(props.projectId)
  } catch {
    /* Seed 重建失败不应阻塞退出 */
  }
  router.push('/')
}
</script>

<template>
  <div class="chat-workspace">
    <header class="chat-workspace__top">
      <button type="button" class="chat-workspace__exit" @click="handleExit">← 首页</button>
      <div class="chat-workspace__title-block">
        <span class="chat-workspace__title">{{ projectName }}</span>
        <span class="chat-workspace__subtitle">主 Agent · 后台同步</span>
      </div>
      <button
        type="button"
        class="chat-workspace__go-workspace"
        @click="router.push(`/workspace/${projectId}`)"
      >
        打开工作区
      </button>
    </header>

    <main class="chat-workspace__body">
      <ChatSessionSidebar />

      <section class="chat-workspace__chat">
        <div ref="streamRef" class="chat-workspace__stream">
          <p v-if="messages.length === 0 && !streamingReply && !isStreaming" class="chat-workspace__empty">
            开始一场对话：主 Agent 会在后台引导创作、抽取实体并建议结构。
          </p>

          <div
            v-for="message in messages"
            :key="message.id"
            class="chat-msg"
            :class="`chat-msg--${message.role}`"
          >
            <span v-if="message.role === 'assistant' && message.agentType" class="chat-msg__agent">
              {{ AGENT_LABELS[message.agentType] ?? message.agentType }}
            </span>
            <div
              v-if="message.role === 'assistant'"
              class="chat-msg__bubble chat-msg__bubble--md"
              v-html="renderMarkdown(message.content)"
            ></div>
            <div v-else class="chat-msg__bubble">{{ message.content }}</div>
            <AgentTracePanel
              v-if="message.role === 'assistant' && message.trace?.length"
              :items="message.trace"
            />
            <ProviderThinkingPanel
              v-if="message.role === 'assistant' && message.providerThinking"
              :content="message.providerThinking"
            />
            <div v-if="message.webSources?.length" class="chat-msg__sources">
              <WebSourceCard
                v-for="(source, index) in message.webSources"
                :key="`${message.id}-src-${index}`"
                :source="source"
              />
            </div>
            <div v-if="message.applied?.length" class="chat-msg__applied">
              <InlineEntityCard
                v-for="item in message.applied"
                :key="item.node_id"
                :item="item"
                @edit="(id, patch) => chat.editAppliedNode(id, patch)"
                @remove="(id) => chat.removeAppliedNode(id)"
              />
            </div>
          </div>

          <div v-if="streamingReply || streamingApplied.length" class="chat-msg chat-msg--assistant">
            <div
              v-if="streamingReply"
              class="chat-msg__bubble chat-msg__bubble--md"
              v-html="renderMarkdown(streamingReply)"
            ></div>
            <AgentTracePanel :items="streamingTrace" />
            <ProviderThinkingPanel :content="streamingProviderThinking" />
            <div v-if="streamingWebSources.length" class="chat-msg__sources">
              <WebSourceCard
                v-for="(source, index) in streamingWebSources"
                :key="`stream-src-${index}`"
                :source="source"
              />
            </div>
            <div v-if="streamingApplied.length" class="chat-msg__applied">
              <InlineEntityCard
                v-for="item in streamingApplied"
                :key="item.node_id"
                :item="item"
                @edit="(id, patch) => chat.editAppliedNode(id, patch)"
                @remove="(id) => chat.removeAppliedNode(id)"
              />
            </div>
          </div>
          <div v-else-if="isStreaming" class="chat-workspace__thinking">
            <span v-if="lastAgent" class="chat-workspace__thinking-agent">
              {{ AGENT_LABELS[lastAgent] ?? lastAgent }}
            </span>
            <span>{{ progressLabel || '思考中' }}</span>
            <span class="chat-workspace__dots" aria-hidden="true"><i></i><i></i><i></i></span>
          </div>
          <AgentTracePanel v-if="isStreaming && !streamingReply" :items="streamingTrace" />
          <ProviderThinkingPanel
            v-if="isStreaming && !streamingReply"
            :content="streamingProviderThinking"
          />
          <p v-if="error" class="chat-workspace__error">{{ error }}</p>
        </div>

        <div class="chat-composer--dock">
          <form class="chat-composer" @submit.prevent="handleSend">
            <input
              v-model="draft"
              class="chat-composer__field"
              type="text"
              placeholder="说说你正在想什么，灵感会在后台整理成结构…"
              :disabled="isStreaming"
            />
            <button
              type="submit"
              class="chat-composer__send"
              :class="{ 'is-ready': hasContent }"
              aria-label="发送"
              :disabled="isStreaming"
            >
              <span v-if="isStreaming" class="chat-composer__send-loading" aria-hidden="true">…</span>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true" class="chat-composer__send-icon">
                <path
                  d="M12 19V5M12 5l-5.5 5.5M12 5l5.5 5.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </form>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.chat-workspace {
  height: 100vh;
  display: grid;
  grid-template-rows: 56px minmax(0, 1fr);
  background: var(--app-bg, #fff);
}

.chat-workspace__top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border, #e5e7eb);
  background: var(--panel, #fafafa);
}

.chat-workspace__title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-workspace__title {
  font-weight: 700;
  font-size: 15px;
}

.chat-workspace__subtitle {
  font-size: 11px;
  color: var(--muted, #888);
}

.chat-workspace__exit,
.chat-workspace__go-workspace {
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border, #ddd);
  background: var(--app-bg, #fff);
  cursor: pointer;
  font-size: 13px;
}

.chat-workspace__go-workspace:hover,
.chat-workspace__exit:hover {
  border-color: var(--accent-border);
  color: var(--accent-deep);
}

.chat-workspace__body {
  min-height: 0;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
}

.chat-workspace__chat {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
}

.chat-workspace__stream {
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat-workspace__empty {
  margin: 0;
  color: var(--muted, #888);
  font-size: 13px;
  line-height: 1.6;
}

.chat-msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 82%;
}

.chat-msg--user {
  align-self: flex-end;
  align-items: flex-end;
}

.chat-msg__agent {
  display: inline-flex;
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent, #8b5cf6);
  color: #fff;
}

.chat-msg__bubble {
  padding: 10px 14px;
  border-radius: 12px;
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 14px;
}

.chat-msg--assistant .chat-msg__bubble {
  background: var(--accent-soft, rgba(139, 92, 246, 0.08));
  color: var(--text);
}

.chat-msg--user .chat-msg__bubble {
  background: var(--accent);
  color: #fff;
}

.chat-msg__bubble--md {
  white-space: normal;
}

.chat-msg__bubble--md :deep(p) {
  margin: 0 0 8px;
}

.chat-msg__bubble--md :deep(p:last-child) {
  margin-bottom: 0;
}

.chat-msg__bubble--md :deep(ul),
.chat-msg__bubble--md :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 18px;
}

.chat-msg__bubble--md :deep(strong) {
  font-weight: 600;
}

.chat-msg__bubble--md :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}

.chat-msg__bubble--md :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  padding: 8px 10px;
  border-radius: 8px;
  overflow-x: auto;
}

.chat-msg__applied,
.chat-msg__sources {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-workspace__thinking {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--accent, #8b5cf6);
  background: var(--accent-soft, rgba(139, 92, 246, 0.1));
}

.chat-workspace__thinking-agent {
  font-weight: 700;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent, #8b5cf6);
  color: #fff;
}

.chat-workspace__dots {
  display: inline-flex;
  gap: 3px;
}

.chat-workspace__dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: thinking-bounce 1.2s ease-in-out infinite;
}

.chat-workspace__dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.chat-workspace__dots i:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes thinking-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.chat-workspace__error {
  color: #dc2626;
  font-size: 13px;
}
</style>
