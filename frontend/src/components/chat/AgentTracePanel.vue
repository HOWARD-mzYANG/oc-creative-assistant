<script setup lang="ts">
import type { AgentTraceItemDto } from '../../api/chatApi'

defineProps<{
  items: AgentTraceItemDto[]
}>()
</script>

<template>
  <details v-if="items.length" class="agent-trace">
    <summary class="agent-trace__summary">
      <span>处理过程</span>
      <span class="agent-trace__count">{{ items.length }}</span>
    </summary>
    <ol class="agent-trace__list">
      <li v-for="(item, index) in items" :key="`${item.node}-${index}`" class="agent-trace__item">
        <span class="agent-trace__title">{{ item.title }}</span>
        <p class="agent-trace__content">{{ item.content }}</p>
      </li>
    </ol>
  </details>
</template>

<style scoped>
.agent-trace {
  width: 100%;
  margin-top: 4px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  background: var(--panel, #fafafa);
  color: var(--text-soft, #555);
}

.agent-trace__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 9px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.agent-trace__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--accent-soft, rgba(139, 92, 246, 0.12));
  color: var(--accent-deep, #6d28d9);
  font-size: 11px;
}

.agent-trace__list {
  margin: 0;
  padding: 0 9px 8px 24px;
}

.agent-trace__item {
  margin-top: 7px;
  padding-left: 2px;
}

.agent-trace__title {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text, #222);
}

.agent-trace__content {
  margin: 3px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.55;
}
</style>
