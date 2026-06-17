<script setup lang="ts">
import { computed, inject } from 'vue'
import { EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@vue-flow/core'
import type { CreativeEdgeData } from '../../../types/node'
import InlineEditableText from '../InlineEditableText.vue'

const props = defineProps<EdgeProps<CreativeEdgeData>>()
const updateEdgeLabel = inject<(edgeId: string, label: string) => void>('updateEdgeLabel')

const path = computed(() =>
  getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  }),
)

const edgePath = computed(() => path.value[0])
const labelX = computed(() => path.value[1])
const labelY = computed(() => path.value[2])
/** EdgeProps.label 是联合类型（string | VNode | …）；这里只渲染普通字符串标签。 */
const labelText = computed(() => (typeof props.label === 'string' ? props.label : ''))
</script>

<template>
  <path
    :id="id"
    :d="edgePath"
    :marker-end="markerEnd"
    :style="style"
    class="vue-flow__edge-path"
    fill="none"
  />

  <EdgeLabelRenderer v-if="labelText.trim()">
    <div
      class="vue-flow__edge-text-wrapper nodrag nopan"
      :style="{
        transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
      }"
    >
    <InlineEditableText
        :style="labelStyle"
        :model-value="labelText"
        placeholder="关系标签"
        @save="(value: string) => updateEdgeLabel?.(id, value)"
      />
    </div>
  </EdgeLabelRenderer>
</template>

<style scoped>
.vue-flow__edge-text-wrapper {
  position: absolute;
  pointer-events: all;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.92);
  font-size: 12px;
  font-weight: 700;
}
</style>
