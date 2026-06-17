<script setup lang="ts">
import type { AiOutput } from '../../stores/useAiOutputStore'

/**
 * 单张 AI 输出卡片（second_revision 变更 B / W5）。
 * 顶部展示来源类型标签，并支持折叠 / 展开；内容可长可短。
 */
defineProps<{ output: AiOutput }>()
const emit = defineEmits<{ toggle: [id: string] }>()

const TYPE_META: Record<string, { icon: string; label: string }> = {
  search: { icon: '🌐', label: '网页搜索' },
  rag: { icon: '📚', label: '记忆' },
  question: { icon: '💡', label: '提示' },
  feedback: { icon: '✨', label: '反馈' },
}
</script>

<template>
  <article class="ai-card" :class="`ai-card--${output.type}`">
    <header class="ai-card__head" @click="emit('toggle', output.id)">
      <span class="ai-card__tag">
        {{ (TYPE_META[output.type] ?? { icon: '·', label: output.type }).icon }}
        {{ (TYPE_META[output.type] ?? { icon: '·', label: output.type }).label }}
      </span>
      <span class="ai-card__caret">{{ output.collapsed ? '▸' : '▾' }}</span>
    </header>
    <p v-if="!output.collapsed" class="ai-card__content">{{ output.content }}</p>
  </article>
</template>

<style scoped>
.ai-card {
  border: 1px solid var(--border, #e5e7eb);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fff;
}
.ai-card--search {
  border-left-color: #0ea5e9;
}
.ai-card--rag {
  border-left-color: #8b5cf6;
}
.ai-card--question {
  border-left-color: #f59e0b;
}
.ai-card--feedback {
  border-left-color: #10b981;
}
.ai-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.ai-card__tag {
  font-size: 12px;
  color: var(--accent-deep);
}
.ai-card__caret {
  font-size: 11px;
  color: var(--muted, #999);
}
.ai-card__content {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>
