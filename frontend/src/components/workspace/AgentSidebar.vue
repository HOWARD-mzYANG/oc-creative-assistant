<script setup lang="ts">
import type { CreativeFlowEdge, CreativeFlowNode } from '../../types/node'
import EdgeDetailPanel from './EdgeDetailPanel.vue'
import NodeDetailPanel from './NodeDetailPanel.vue'

/**
 * 右侧详情面板的轻量路由容器。
 *
 * 选中节点时挂载 NodeDetailPanel，选中边时挂载 EdgeDetailPanel；未选中时显示空状态。
 * 所有编辑事件会原样向外转发，实际持久化由父级 AppShell 处理。
 */
defineProps<{
  selectedNode: CreativeFlowNode | null
  selectedEdge: CreativeFlowEdge | null
  nodes: CreativeFlowNode[]
}>()

const emit = defineEmits<{
  'node-updated': [node: CreativeFlowNode]
  'node-deleted': [nodeId: string]
  'edge-updated': [edge: CreativeFlowEdge]
  'edge-deleted': [edgeId: string]
}>()

/** 说明 forwardNodeUpdated 的局部业务逻辑。 */
function forwardNodeUpdated(node: CreativeFlowNode) {
  emit('node-updated', node)
}

/** 说明 forwardNodeDeleted 的局部业务逻辑。 */
function forwardNodeDeleted(nodeId: string) {
  emit('node-deleted', nodeId)
}

/** 说明 forwardEdgeUpdated 的局部业务逻辑。 */
function forwardEdgeUpdated(edge: CreativeFlowEdge) {
  emit('edge-updated', edge)
}

/** 说明 forwardEdgeDeleted 的局部业务逻辑。 */
function forwardEdgeDeleted(edgeId: string) {
  emit('edge-deleted', edgeId)
}
</script>

<template>
  <aside class="detail-sidebar">
    <NodeDetailPanel
      v-if="selectedNode"
      :selected-node="selectedNode"
      @node-updated="forwardNodeUpdated"
      @node-deleted="forwardNodeDeleted"
    />

    <EdgeDetailPanel
      v-else-if="selectedEdge"
      :selected-edge="selectedEdge"
      :nodes="nodes"
      @edge-updated="forwardEdgeUpdated"
      @edge-deleted="forwardEdgeDeleted"
    />

    <section v-else class="empty-state">
      <p>未选择内容</p>
      <span>选择一个节点来编辑内容，或选择一条边来编辑关系标签。</span>
    </section>
  </aside>
</template>

<style scoped src="./AgentSidebar.scoped.css"></style>
