<script setup lang="ts">
import { markRaw, nextTick, ref, watch } from 'vue'
import { VueFlow, useVueFlow, type Edge } from '@vue-flow/core'
import type { CreativeFlowNode } from '../../../types/node'
import { applyTreeLayout, hierarchyToTreeCanvasEdges } from '../../../utils/worldHierarchy'
import WorldNode from '../../nodes/WorldNode.vue'
import CreativeBezierEdge from '../../canvas/edges/CreativeBezierEdge.vue'

const props = defineProps<{
  nodes: CreativeFlowNode[]
  selectedId: string
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const FLOW_ID = 'oc-world-tree-flow'

const nodeTypes = {
  worldbuilding: markRaw(WorldNode),
}

const flowNodes = ref<CreativeFlowNode[]>([])
const flowEdges = ref<Edge[]>([])

const { fitView, onNodesInitialized } = useVueFlow({ id: FLOW_ID })

/** 说明 rebuildGraph 的局部业务逻辑。 */
function rebuildGraph() {
  const laid = applyTreeLayout(props.nodes)
  flowNodes.value = laid.map((node) => ({
    ...node,
    type: 'worldbuilding',
    selected: node.id === props.selectedId,
  }))
  flowEdges.value = hierarchyToTreeCanvasEdges(laid) as unknown as Edge[]
}

/** 说明 refit 的局部业务逻辑。 */
function refit() {
  void nextTick(() => {
    requestAnimationFrame(() => {
      void fitView({ padding: 0.28, duration: 240 })
    })
  })
}

/** 说明 hierarchySignature 的局部业务逻辑。 */
function hierarchySignature(nodes: CreativeFlowNode[]) {
  return nodes
    .map((node) => `${node.id}:${node.data.parentId ?? ''}:${node.data.sortOrder ?? 0}:${node.data.title}`)
    .sort()
    .join('|')
}

watch(
  () => hierarchySignature(props.nodes),
  () => {
    rebuildGraph()
    refit()
  },
  { immediate: true },
)

watch(
  () => props.selectedId,
  (id) => {
    flowNodes.value = flowNodes.value.map((node) => ({
      ...node,
      selected: node.id === id,
    }))
  },
)

onNodesInitialized(() => {
  refit()
})

watch(
  () => flowNodes.value.length,
  () => {
    if (flowNodes.value.length > 0) refit()
  },
)
</script>

<template>
  <VueFlow
    :id="FLOW_ID"
    v-model:nodes="flowNodes"
    v-model:edges="flowEdges"
    class="world-tree-flow"
    :node-types="nodeTypes"
    :default-viewport="{ x: 0, y: 0, zoom: 0.9 }"
    :min-zoom="0.35"
    :max-zoom="1.4"
    :nodes-draggable="false"
    :nodes-connectable="false"
    :elements-selectable="true"
    :pan-on-drag="[0, 1]"
    :fit-view-on-init="true"
    @node-click="({ node }) => emit('select', node.id)"
  >
    <template #node-worldbuilding="nodeProps">
      <WorldNode v-bind="nodeProps" />
    </template>
    <template #edge-bezier="edgeProps">
      <CreativeBezierEdge v-bind="edgeProps" />
    </template>
  </VueFlow>
</template>

<style scoped>
.world-tree-flow {
  width: 100%;
  height: 100%;
  background-color: var(--canvas-bg);
  background-image:
    radial-gradient(circle at 18% 22%, rgba(233, 130, 74, 0.1), transparent 42%),
    radial-gradient(var(--grid-line) 1.6px, transparent 1.6px);
  background-size: 100% 100%, 24px 24px;
}

:deep(.vue-flow__pane) {
  cursor: grab;
}

:deep(.vue-flow__pane.dragging) {
  cursor: grabbing;
}

:deep(.vue-flow__node) {
  pointer-events: all;
}

:deep(.vue-flow__edge-path) {
  stroke-width: 2.4;
  stroke-linecap: round;
}

:deep(.vue-flow__edge.selected .vue-flow__edge-path),
:deep(.vue-flow__edge:hover .vue-flow__edge-path) {
  stroke-width: 2.8;
}
</style>
