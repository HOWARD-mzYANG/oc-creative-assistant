<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { marked } from 'marked'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useChatStore } from '../../stores/useChatStore'
import { useNodeNavStore } from '../../stores/useNodeNavStore'
import AgentTracePanel from '../chat/AgentTracePanel.vue'
import InlineEntityCard from '../chat/InlineEntityCard.vue'
import ProviderThinkingPanel from '../chat/ProviderThinkingPanel.vue'
import WebSourceCard from '../chat/WebSourceCard.vue'
import PanelToggleButton from './PanelToggleButton.vue'

marked.use({ gfm: true, breaks: true })

function renderMarkdown(text: string): string {
  return marked.parse(text) as string
}

defineEmits<{ collapse: [] }>()

const chat = useChatStore()
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

const router = useRouter()
const nodeNav = useNodeNavStore()

function goToNode(node: { id: string; title: string; node_type: string }) {
  const pid = chat.projectId
  if (!pid) return
  if (node.node_type === 'character') {
    router.push(`/workspace/${pid}/characters/${node.id}`)
    return
  }
  // plot / worldbuilding: jump to the board and focus the node on its canvas
  nodeNav.request(node.id)
  router.push(
    node.node_type === 'worldbuilding'
      ? `/workspace/${pid}/world`
      : `/workspace/${pid}/plot`,
  )
}

const AGENT_LABELS: Record<string, string> = {
  inspiration: '灵感',
  research: '资料',
  structure: '结构',
  simulation: '模拟',
  small_talk: '闲聊',
}

/* ---- chat auto-scroll ---- */
const streamRef = ref<HTMLElement | null>(null)
async function scrollToBottom() {
  await nextTick()
  if (streamRef.value) streamRef.value.scrollTop = streamRef.value.scrollHeight
}
watch(
  [messages, streamingReply, streamingTrace, streamingProviderThinking, streamingApplied],
  scrollToBottom,
  { deep: true },
)
</script>

<template>
  <aside class="right-stage">
    <header class="right-stage__head">
      <span class="right-stage__title">Agent</span>
      <PanelToggleButton
        direction="right"
        expanded
        label="收起 Agent 面板"
        @click="$emit('collapse')"
      />
    </header>

    <div class="right-stage__body">
      <div ref="streamRef" class="right-stage__chat">
        <p v-if="messages.length === 0 && !streamingReply && !isStreaming" class="right-stage__empty">
          在下方输入框提问。Agent 可以协助引导、抽取实体并提出结构建议。
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
          <div v-if="message.relatedNodes?.length" class="chat-msg__related">
            <span class="chat-msg__related-label">相关节点</span>
            <button
              v-for="rn in message.relatedNodes"
              :key="rn.id"
              type="button"
              class="chat-msg__related-chip"
              @click="goToNode(rn)"
            >
              {{ rn.title }}
            </button>
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
        <div v-else-if="isStreaming" class="right-stage__thinking">
          <span v-if="lastAgent" class="right-stage__thinking-agent">
            {{ AGENT_LABELS[lastAgent] ?? lastAgent }}
          </span>
          <span class="right-stage__thinking-label">{{ progressLabel || '思考中' }}</span>
          <span class="right-stage__dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </div>
        <AgentTracePanel v-if="isStreaming && !streamingReply" :items="streamingTrace" />
        <ProviderThinkingPanel
          v-if="isStreaming && !streamingReply"
          :content="streamingProviderThinking"
        />
        <p v-if="error" class="right-stage__error">{{ error }}</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.right-stage {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border, #e5e7eb);
  overflow: hidden;
}

.right-stage__head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #e5e7eb);
}
.right-stage__title {
  font-size: 14px;
}

.right-stage__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.right-stage__chat {
  min-width: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* messages */
.right-stage__empty {
  margin: 0;
  color: var(--muted, #888);
  font-size: 13px;
  line-height: 1.6;
}
.right-stage__thinking {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--accent, #8b5cf6);
  background: var(--accent-soft, rgba(139, 92, 246, 0.1));
  animation: thinking-pulse 1.8s ease-in-out infinite;
}
.right-stage__thinking-agent {
  font-weight: 700;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent, #8b5cf6);
  color: #fff;
}
.right-stage__thinking-label {
  font-weight: 500;
}
.right-stage__dots {
  display: inline-flex;
  gap: 3px;
}
.right-stage__dots i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.right-stage__dots i:nth-child(2) {
  animation-delay: 0.15s;
}
.right-stage__dots i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes thinking-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}
@keyframes thinking-pulse {
  0%, 100% { opacity: 0.85; }
  50% { opacity: 1; }
}
.right-stage__error {
  margin: 0;
  color: #dc2626;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat-msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 100%;
}
.chat-msg--user {
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
  padding: 8px 11px;
  border-radius: 10px;
  white-space: pre-wrap;
  line-height: 1.55;
  font-size: 13px;
  max-width: 100%;
  word-break: break-word;
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
.chat-msg__bubble--md :deep(h1),
.chat-msg__bubble--md :deep(h2),
.chat-msg__bubble--md :deep(h3) {
  font-size: 14px;
  margin: 8px 0 4px;
}
.chat-msg--assistant .chat-msg__bubble {
  background: var(--accent-soft, rgba(139, 92, 246, 0.08));
  color: var(--text);
}
.chat-msg--user .chat-msg__bubble {
  background: var(--accent);
  color: #fff;
}
.chat-msg__applied,
.chat-msg__sources {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chat-msg__related {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.chat-msg__related-label {
  font-size: 11px;
  color: var(--muted, #888);
}
.chat-msg__related-chip {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--accent-border, rgba(139, 92, 246, 0.3));
  background: var(--accent-soft, rgba(139, 92, 246, 0.1));
  color: var(--accent-deep, #6d28d9);
  cursor: pointer;
}
.chat-msg__related-chip:hover {
  background: var(--accent, #8b5cf6);
  color: #fff;
}
</style>
