<script setup lang="ts">
defineProps<{
  content: string
}>()
</script>

<template>
  <details v-if="content.trim()" class="provider-thinking" open>
    <summary class="provider-thinking__summary">模型原始思考</summary>
    <pre class="provider-thinking__content">{{ content }}</pre>
  </details>
</template>

<style scoped>
.provider-thinking {
  width: 100%;
  margin-top: 4px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  background: #fff;
  color: var(--text-soft, #555);
}

.provider-thinking__summary {
  padding: 6px 9px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.provider-thinking__content {
  max-height: 220px;
  margin: 0;
  padding: 0 9px 9px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}
</style>
