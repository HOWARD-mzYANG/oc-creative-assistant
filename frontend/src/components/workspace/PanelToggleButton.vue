<script setup lang="ts">
/** 用于折叠 / 展开工作区侧边栏的小箭头按钮。 */
defineProps<{
  direction: 'left' | 'right'
  expanded: boolean
  label: string
}>()

defineEmits<{ click: [] }>()
</script>

<template>
  <button
    type="button"
    class="panel-toggle"
    :aria-label="label"
    :title="label"
    @click="$emit('click')"
  >
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <!-- 折叠左侧面板。 -->
      <template v-if="direction === 'left'">
        <polyline v-if="expanded" points="15 18 9 12 15 6" />
        <polyline v-else points="9 18 15 12 9 6" />
      </template>
      <!-- 折叠右侧面板。 -->
      <template v-else>
        <polyline v-if="expanded" points="9 18 15 12 9 6" />
        <polyline v-else points="15 18 9 12 15 6" />
      </template>
    </svg>
  </button>
</template>

<style scoped>
.panel-toggle {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  transition:
    background 0.16s ease,
    color 0.16s ease,
    border-color 0.16s ease,
    transform 0.12s ease;
}

.panel-toggle:hover {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.panel-toggle:active {
  transform: scale(0.94);
}

.panel-toggle svg {
  width: 16px;
  height: 16px;
}
</style>
