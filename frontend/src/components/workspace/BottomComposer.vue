<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useComposerStore } from '../../stores/useComposerStore'
import { useChatStore } from '../../stores/useChatStore'
import QuotedNodeChip from './QuotedNodeChip.vue'

/**
 * 常驻底部输入框：发送到主 LangGraph 智能体（聊天流 + 抽取）。
 */
const composer = useComposerStore()
const chat = useChatStore()
const { references, input, collapsed, webSearchMode } = storeToRefs(composer)
const { isStreaming, progressLabel } = storeToRefs(chat)

const isSending = ref(false)

const hasContent = computed(
  () => Boolean(input.value.trim()) || references.value.length > 0,
)

const webSearchTitle = computed(() => {
  if (webSearchMode.value === 'on') return '联网搜索：强制开启（点击切换）'
  if (webSearchMode.value === 'off') return '联网搜索：已关闭（点击切换）'
  return '联网搜索：自动判断（点击切换）'
})

function toggleCollapsed() {
  composer.setCollapsed(!collapsed.value)
}

async function handleSend() {
  const message = input.value.trim()
  const quotedIds = references.value.map((r) => r.id)
  if ((!message && quotedIds.length === 0) || isSending.value || isStreaming.value) return

  isSending.value = true
  try {
    const text =
      message ||
      `请参考这 ${quotedIds.length} 个引用节点，帮我继续展开。`
    await chat.send(text, quotedIds, webSearchMode.value)
    composer.$patch({ input: '', references: [] })
  } finally {
    isSending.value = false
  }
}
</script>

<template>
  <div class="composer-wrap" :class="{ 'is-collapsed': collapsed }">
    <button
      type="button"
      class="composer-handle"
      :aria-label="collapsed ? '展开输入框' : '收起输入框'"
      :title="collapsed ? '展开输入框' : '收起输入框'"
      @click="toggleCollapsed"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <polyline
          v-if="collapsed"
          points="6 15 12 9 18 15"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <polyline
          v-else
          points="6 9 12 15 18 9"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <div v-show="!collapsed" class="composer-body">
      <p v-if="isStreaming && progressLabel" class="composer__status">{{ progressLabel }}</p>

      <div v-if="references.length" class="composer__refs">
        <QuotedNodeChip
          v-for="ref in references"
          :key="ref.id"
          :node="ref"
          @remove="composer.removeReference"
        />
      </div>

      <form class="chat-composer" @submit.prevent="handleSend">
        <button
          type="button"
          class="composer__web"
          :class="{
            'is-on': webSearchMode === 'on',
            'is-off': webSearchMode === 'off',
          }"
          :title="webSearchTitle"
          :aria-label="webSearchTitle"
          :disabled="isStreaming"
          @click="composer.cycleWebSearchMode()"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" class="composer__web-icon">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.75" />
            <path
              d="M3 12h18M12 3c2.5 2.8 4 6 4 9s-1.5 6.2-4 9M12 3c-2.5 2.8-4 6-4 9s1.5 6.2 4 9"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
              stroke-linecap="round"
            />
            <path
              v-if="webSearchMode === 'off'"
              d="M5 5l14 14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
        </button>
        <input
          v-model="input"
          class="chat-composer__field"
          type="text"
          placeholder="和智能体对话，也可以在画布中按 Ctrl+C 引用节点…"
          :disabled="isStreaming"
        />
        <button
          type="submit"
          class="chat-composer__send"
          :class="{ 'is-ready': hasContent }"
          aria-label="发送"
          :disabled="isSending || isStreaming"
        >
          <span v-if="isSending || isStreaming" class="chat-composer__send-loading" aria-hidden="true">…</span>
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
  </div>
</template>

<style scoped>
.composer-wrap {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  background: var(--app-bg);
  padding: 12px 16px;
}

.composer-wrap.is-collapsed {
  padding: 0;
  height: 0;
  border-top: 1px solid var(--border);
  overflow: visible;
}

.composer-wrap.is-collapsed .composer-handle {
  top: -8px;
}

/* 顶部分隔线上的小箭头，居中显示。 */
.composer-handle {
  position: absolute;
  top: 0;
  left: 50%;
  z-index: 2;
  transform: translate(-50%, -50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 12px;
  padding: 0;
  border: none;
  background: var(--app-bg);
  color: var(--muted);
  cursor: pointer;
  line-height: 0;
  transition: color 0.15s ease;
}

.composer-handle:hover {
  color: var(--accent);
}

.composer-handle svg {
  width: 11px;
  height: 11px;
}

.composer-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.composer__status {
  margin: 0;
  font-size: 11px;
  color: var(--muted);
}

.composer__refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.composer__web {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.composer__web:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent-border);
}

.composer__web.is-on {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.composer__web.is-off {
  color: var(--muted);
  background: var(--app-bg);
  opacity: 0.85;
}

.composer__web:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.composer__web-icon {
  width: 18px;
  height: 18px;
}
</style>
