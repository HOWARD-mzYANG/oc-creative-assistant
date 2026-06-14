<script setup lang="ts">
import type { CreativeFlowNode } from '../../../types/node'
import WorldTreeFlowInner from './WorldTreeFlowInner.vue'

defineProps<{
  nodes: CreativeFlowNode[]
  selectedId: string
  active: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
}>()
</script>

<template>
  <div class="world-tree-canvas">
    <WorldTreeFlowInner
      v-if="active && nodes.length > 0"
      :nodes="nodes"
      :selected-id="selectedId"
      @select="emit('select', $event)"
    />

    <p v-if="nodes.length === 0" class="world-tree-canvas__empty">
      还没有笔记，请在“笔记”视图添加根笔记。
    </p>
    <p v-else-if="active" class="world-tree-canvas__hint">
      Hierarchy only · click a node to edit in Notes view
    </p>
  </div>
</template>

<style scoped>
.world-tree-canvas {
  position: relative;
  height: 100%;
  min-height: 0;
  background:
    radial-gradient(circle at 50% 0%, rgba(233, 130, 74, 0.06), transparent 55%),
    var(--canvas-bg);
}

.world-tree-canvas__hint,
.world-tree-canvas__empty {
  position: absolute;
  left: 14px;
  bottom: 12px;
  margin: 0;
  font-size: 0.68rem;
  color: var(--muted);
  opacity: 0.55;
  pointer-events: none;
}
</style>
