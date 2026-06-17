<script setup lang="ts">
import type { QuotedNodeRef } from '../../stores/useComposerStore'

/**
 * 底部输入框中的引用节点小标签（second_revision 变更 C）。
 * 展示类型图标 + 节点名称，并提供 X 按钮移除。
 */
defineProps<{ node: QuotedNodeRef; removable?: boolean }>()
const emit = defineEmits<{ remove: [id: string] }>()

const TYPE_ICON: Record<string, string> = {
  character: '👤',
  plot: '🧩',
  world: '🌍',
  worldbuilding: '🌍',
  idea: '💡',
  research: '📚',
  structure: '🗂',
}
</script>

<template>
  <span class="quoted-chip">
    {{ TYPE_ICON[node.type] ?? '📌' }} {{ node.title }}
    <button
      v-if="removable !== false"
      type="button"
      class="quoted-chip__x"
      @click="emit('remove', node.id)"
    >
      ✕
    </button>
  </span>
</template>

<style scoped>
.quoted-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-deep);
}
.quoted-chip__x {
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
}
</style>
