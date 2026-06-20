<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { ConnectionMode, SelectionMode, VueFlow, useVueFlow } from '@vue-flow/core'
import type { Edge, NodeMouseEvent } from '@vue-flow/core'
import type {
  CreativeFlowEdge,
  CreativeFlowNode,
  CreativeGraphSnapshot,
  CreativeNodeType,
  CreativeRelationType,
} from '../../types/node'
import {
  DEFAULT_RELATION_TYPE,
  cloneNode,
  getRelationLabel,
  normalizeEdge,
} from '../../utils/canvasRelations'
import { useCanvasGraph } from '../../composables/useCanvasGraph'
import { useComposerStore } from '../../stores/useComposerStore'
import { useCenterStageStore } from '../../stores/useCenterStageStore'
import CanvasContextMenu from './CanvasContextMenu.vue'
import EdgeRelationMenu from './EdgeRelationMenu.vue'
import CharacterNode from '../nodes/CharacterNode.vue'
import IdeaNode from '../nodes/IdeaNode.vue'
import PlotNode from '../nodes/PlotNode.vue'
import ResearchNode from '../nodes/ResearchNode.vue'
import StructureNode from '../nodes/StructureNode.vue'
import WorldNode from '../nodes/WorldNode.vue'
import CreativeBezierEdge from './edges/CreativeBezierEdge.vue'

const FLOW_ID = 'oc-main-flow'

/**
 * 创意画布组件。
 *
 * 负责 Vue Flow 运行时交互、节点渲染，以及外部 props（graphVersion / createNodeRequest /
 * highlightedXxxIds）与本地节点 / 边状态的同步；增删改图谱内容的核心操作放在
 * useCanvasGraph，关系类型、节点克隆等纯函数放在 utils/canvasRelations。
 */
const props = defineProps<{
  selectedNodeId: string
  selectedEdgeId?: string
  initialNodes: CreativeFlowNode[]
  initialEdges: CreativeFlowEdge[]
  graphVersion: number
  createNodeRequest: { type: CreativeNodeType; nonce: number } | null
  focusNodeRequest?: { id: string; nonce: number } | null
  /* 刚出现的 ID：AppShell 在暂存项接受后通过 diff 计算，动画结束后清空。 */
  highlightedNodeIds: string[]
  highlightedEdgeIds: string[]
  /* 空白处右键可创建的节点类型；SubgraphCanvas 按子图传入，未提供时默认允许全部类型。 */
  createTypes?: CreativeNodeType[]
}>()

const emit = defineEmits<{
  nodeSelected: [nodeId: string]
  edgeSelected: [edgeId: string]
  nodeAdded: [node: CreativeFlowNode]
  graphChanged: [snapshot: CreativeGraphSnapshot]
}>()

const flowShell = ref<HTMLElement | null>(null)
const isMiddleMouseDown = ref(false)
const selectedRelationType = ref<CreativeRelationType>(DEFAULT_RELATION_TYPE)
const isRelationSelectOpen = ref(false)
const skipNextFocus = ref(false)

/** 关闭目标视图或弹层。 */
function closeAllSelects(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.custom-select-container')) {
    isRelationSelectOpen.value = false
  }
  if (!target.closest('.ctx-menu')) {
    contextMenu.value.show = false
  }
  if (!target.closest('.edge-relation-menu')) {
    edgeRelationMenu.value.show = false
  }
}

/** 响应对应的 DOM 或组件事件。 */
function onFlowShellMouseDown(event: MouseEvent) {
  if (event.button !== 1) return
  event.preventDefault()
  isMiddleMouseDown.value = true
}

/** 响应对应的 DOM 或组件事件。 */
function onFlowShellMouseUp(event: MouseEvent) {
  if (event.button === 1) {
    isMiddleMouseDown.value = false
  }
}

/** 清空当前状态或选择。 */
function clearMiddleMousePan() {
  isMiddleMouseDown.value = false
}

onMounted(() => {
  document.addEventListener('click', closeAllSelects)
  window.addEventListener('keydown', handleCopyKey, true)
  flowShell.value?.addEventListener('mousedown', onFlowShellMouseDown)
  window.addEventListener('mouseup', onFlowShellMouseUp)
  window.addEventListener('blur', clearMiddleMousePan)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAllSelects)
  window.removeEventListener('keydown', handleCopyKey, true)
  flowShell.value?.removeEventListener('mousedown', onFlowShellMouseDown)
  window.removeEventListener('mouseup', onFlowShellMouseUp)
  window.removeEventListener('blur', clearMiddleMousePan)
})

const nodes = ref<CreativeFlowNode[]>(
  props.initialNodes.map((node) =>
    cloneNode(node, props.selectedNodeId, new Set(props.highlightedNodeIds)),
  ),
)
const edges = ref<CreativeFlowEdge[]>(
  props.initialEdges.map((edge) => normalizeEdge(edge, new Set(props.highlightedEdgeIds))),
)

/* 固定 flow id，确保工具栏操作绑定到当前画布实例，不被页面上的其他 Vue Flow 实例接管。 */
const {
  fitView,
  getViewport,
  setCenter,
  zoomIn,
  zoomOut,
  findEdge,
  onPaneContextMenu,
  onNodeContextMenu,
  onEdgeContextMenu,
  onSelectionContextMenu,
  onNodeDoubleClick,
  screenToFlowCoordinate,
  getSelectedNodes,
} = useVueFlow({ id: FLOW_ID })

const {
  handleCreateNode,
  handleAutoArrange,
  handleClearCanvas,
  handleConnect,
  handleEdgeUpdate,
  handleNodeDragStop,
  updateEdgeRelation,
  updateEdgeLabel,
  updateNodeData,
  removeNode,
  removeEdge,
} = useCanvasGraph({
  nodes,
  edges,
  flowShell,
  selectedRelationType,
  getViewport,
  onGraphChanged: (snapshot) => emit('graphChanged', snapshot),
  onNodeAdded: (node) => emit('nodeAdded', node),
  onNodeSelected: (id) => emit('nodeSelected', id),
  onEdgeSelected: (id) => emit('edgeSelected', id),
})

provide('updateNodeData', updateNodeData)
provide('updateEdgeLabel', updateEdgeLabel)

const composer = useComposerStore()
const centerStage = useCenterStageStore()

const ALL_NODE_TYPES: CreativeNodeType[] = [
  'idea',
  'character',
  'worldbuilding',
  'plot',
  'research',
  'structure',
]
const blankCreateTypes = computed(() => props.createTypes ?? ALL_NODE_TYPES)

const contextMenu = ref<{
  show: boolean
  x: number
  y: number
  type: 'blank' | 'node' | 'edge'
  nodeId: string
  edgeId: string
  edgeLabel: string
}>({ show: false, x: 0, y: 0, type: 'blank', nodeId: '', edgeId: '', edgeLabel: '' })

const edgeRelationMenu = ref<{
  show: boolean
  x: number
  y: number
  edgeId: string
  relationType: CreativeRelationType
}>({ show: false, x: 0, y: 0, edgeId: '', relationType: DEFAULT_RELATION_TYPE })

/** 关闭目标视图或弹层。 */
function closeEdgeRelationMenu() {
  edgeRelationMenu.value.show = false
}

/** 关闭目标视图或弹层。 */
function closeContextMenu() {
  contextMenu.value.show = false
}

/** 说明 pointerFromEvent 的局部业务逻辑。 */
function pointerFromEvent(event: MouseEvent | TouchEvent): { x: number; y: number } {
  if (event instanceof MouseEvent) {
    return { x: event.clientX, y: event.clientY }
  }
  const touch = event.touches[0] ?? event.changedTouches[0]
  return { x: touch?.clientX ?? 0, y: touch?.clientY ?? 0 }
}

/** 保证菜单停留在屏幕内；坐标基于视口（Teleport 到 body）。 */
function clampMenuPosition(x: number, y: number): { x: number; y: number } {
  const pad = 8
  const maxW = 200
  const maxH = 260
  return {
    x: Math.max(pad, Math.min(x, window.innerWidth - maxW - pad)),
    y: Math.max(pad, Math.min(y, window.innerHeight - maxH - pad)),
  }
}

/** 打开目标视图或弹层。 */
function openContextMenu(
  event: MouseEvent | TouchEvent,
  type: 'blank' | 'node' | 'edge',
  target: { nodeId?: string; edgeId?: string; edgeLabel?: string } = {},
) {
  event.preventDefault()
  closeEdgeRelationMenu()
  const { x, y } = pointerFromEvent(event)
  const point = clampMenuPosition(x, y)
  contextMenu.value = {
    show: true,
    x: point.x,
    y: point.y,
    type,
    nodeId: target.nodeId ?? '',
    edgeId: target.edgeId ?? '',
    edgeLabel: target.edgeLabel ?? '',
  }
}

onPaneContextMenu((event) => {
  openContextMenu(event as MouseEvent, 'blank')
})

onNodeContextMenu(({ event, node }) => {
  openContextMenu(event as MouseEvent, 'node', { nodeId: node.id })
})

onEdgeContextMenu(({ event, edge }) => {
  const relationType = (edge.data?.relationType ?? DEFAULT_RELATION_TYPE) as CreativeRelationType
  const label = edge.data?.label || edge.label || getRelationLabel(relationType)
  openContextMenu(event as MouseEvent, 'edge', { edgeId: edge.id, edgeLabel: String(label) })
  skipNextFocus.value = true
  emit('edgeSelected', edge.id)
})

onSelectionContextMenu(({ event, nodes }) => {
  const target = nodes[nodes.length - 1] ?? getSelectedNodes.value.at(-1)
  if (!target) return
  openContextMenu(event, 'node', { nodeId: target.id })
})

// 双击节点：打开中央 NodeDetailView，并带上当前数据快照。
onNodeDoubleClick(({ node }) => {
  centerStage.openDetail(node.id, {
    id: node.id,
    title: node.data?.title ?? '',
    content: node.data?.content ?? '',
    nodeType: (node.data?.nodeType ?? node.type ?? 'idea') as string,
    typeLabel: node.data?.typeLabel ?? '',
    icon: node.data?.icon ?? '',
    tags: [...(node.data?.tags ?? [])],
    status: node.data?.status ?? 'draft',
  })
})

/** 处理对应的用户交互或组件事件。 */
function handleEdgeRelationSelect(relationType: CreativeRelationType) {
  if (!edgeRelationMenu.value.edgeId) return
  updateEdgeRelation(edgeRelationMenu.value.edgeId, relationType)
  closeEdgeRelationMenu()
}

/** 说明 nodeRef 的局部业务逻辑。 */
function nodeRef(nodeId: string) {
  return nodes.value.find((node) => node.id === nodeId)
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuCreate(type: CreativeNodeType) {
  const pos = screenToFlowCoordinate({ x: contextMenu.value.x, y: contextMenu.value.y })
  handleCreateNode(type, { x: pos.x, y: pos.y })
  closeContextMenu()
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuEdit() {
  if (contextMenu.value.nodeId) centerStage.openDetail(contextMenu.value.nodeId)
  closeContextMenu()
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuDuplicate() {
  const src = nodeRef(contextMenu.value.nodeId)
  if (src) {
    handleCreateNode(src.data.nodeType ?? (src.type as CreativeNodeType), {
      x: src.position.x + 40,
      y: src.position.y + 40,
    })
    const created = nodes.value[nodes.value.length - 1]
    if (created) {
      updateNodeData(created.id, {
        title: `${src.data.title} 副本`,
        content: src.data.content,
      })
    }
  }
  closeContextMenu()
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuRemove() {
  if (contextMenu.value.nodeId) removeNode(contextMenu.value.nodeId)
  closeContextMenu()
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuRemoveClick() {
  if (contextMenu.value.type === 'edge') {
    handleMenuEdgeRemove()
  } else {
    handleMenuRemove()
  }
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuEdgeRemove() {
  if (contextMenu.value.edgeId) removeEdge(contextMenu.value.edgeId)
  closeContextMenu()
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuEdgeChangeRelation() {
  const { edgeId, x, y } = contextMenu.value
  if (!edgeId) return
  const edge = edges.value.find((item) => item.id === edgeId)
  const relationType = (edge?.data?.relationType ?? DEFAULT_RELATION_TYPE) as CreativeRelationType
  closeContextMenu()
  requestAnimationFrame(() => {
    edgeRelationMenu.value = { show: true, x, y, edgeId, relationType }
  })
}

/** 说明 quoteNodes 的局部业务逻辑。 */
function quoteNodes(refs: { id: string; type: string; title: string }[]) {
  if (refs.length) composer.addReferences(refs)
}

/** 处理对应的用户交互或组件事件。 */
function handleMenuQuote() {
  const selected = getSelectedNodes.value
  if (selected.length > 1) {
    quoteNodes(
      selected.map((node) => ({
        id: node.id,
        type: (node.data?.nodeType ?? node.type ?? 'idea') as string,
        title: node.data?.title || '未命名',
      })),
    )
  } else {
    const src = nodeRef(contextMenu.value.nodeId)
    if (src) {
      quoteNodes([{ id: src.id, type: src.data.nodeType ?? src.type ?? 'idea', title: src.data.title }])
    }
  }
  closeContextMenu()
}

/** Ctrl/Cmd+C：把当前多选节点复制为引用卡片，放入底部输入框。 */
function handleCopyKey(event: KeyboardEvent) {
  if (!((event.ctrlKey || event.metaKey) && event.key === 'c')) return
  const selected = getSelectedNodes.value
  if (selected.length === 0) return
  event.preventDefault()
  quoteNodes(
    selected.map((node) => ({
      id: node.id,
      type: (node.data?.nodeType ?? node.type ?? 'idea') as string,
      title: node.data?.title || '未命名',
    })),
  )
}

/**
 * 更新画布节点选中状态，并按需移动视口焦点。
 *
 * 视觉选中标记由该组件维护；业务侧的“当前选中项”通过 AppShell 的 props.selectedNodeId
 * 回推进来，形成单向数据流。
 *
 * 参数：
 *   nodeId: 要选中的节点 ID。
 *   shouldFocus: 是否把视口移动到该节点附近。
 */
function selectNode(nodeId: string, shouldFocus = false) {
  for (const node of nodes.value) {
    if (node.data.isActive !== (node.id === nodeId)) {
      node.data.isActive = node.id === nodeId
    }
  }

  if (!shouldFocus) return

  const target = nodes.value.find((node) => node.id === nodeId)
  if (!target) return

  const centerX = target.position.x + 120
  const centerY = target.position.y + 70
  void nextTick(() => {
    void setCenter(centerX, centerY, { duration: 260 })
  })
}

/** 将 Vue Flow 节点点击事件上抛给 AppShell，以维护全局选中状态。 */
function handleNodeClick(event: NodeMouseEvent) {
  skipNextFocus.value = true
  emit('nodeSelected', event.node.id)
}

/** 框选后同步主选中项，并保持 isActive 与 Vue Flow 选中状态一致。 */
function handleSelectionChange(params: { nodes: { id: string }[] }) {
  const selectedIds = new Set(params.nodes.map((node) => node.id))
  for (const node of nodes.value) {
    const active = selectedIds.has(node.id)
    if (node.data.isActive !== active) {
      node.data.isActive = active
    }
  }
  skipNextFocus.value = true
  if (params.nodes.length === 0) {
    emit('nodeSelected', '')
    return
  }
  const primary = params.nodes[params.nodes.length - 1]
  emit('nodeSelected', primary.id)
}

/** 说明 syncEdgePresentation 的局部业务逻辑。 */
function syncEdgePresentation(highlighted = new Set(props.highlightedEdgeIds)) {
  const selectedId = props.selectedEdgeId ?? ''
  edges.value = edges.value.map((edge) =>
    normalizeEdge(edge, highlighted, edge.id === selectedId),
  )
}

/** 将 Vue Flow 边点击事件上抛给 AppShell，以维护全局选中状态。 */
function handleEdgeClick(event: { edge: Edge }) {
  skipNextFocus.value = true
  emit('edgeSelected', event.edge.id)
  syncEdgePresentation()
}

/** 视口适配完整图谱范围，节点变多后更容易找回整体结构。 */
function handleFitView() {
  void fitView({ padding: 0.2, duration: 260 })
}

/** 处理对应的用户交互或组件事件。 */
function handleZoomIn() {
  void zoomIn({ duration: 180 })
}

/** 处理对应的用户交互或组件事件。 */
function handleZoomOut() {
  void zoomOut({ duration: 180 })
}

watch(
  () => props.selectedNodeId,
  (nodeId, oldNodeId) => {
    const fromCanvas = skipNextFocus.value
    skipNextFocus.value = false
    selectNode(nodeId, !fromCanvas && Boolean(oldNodeId && nodeId))
  },
  { immediate: true },
)

watch(
  () => props.selectedEdgeId,
  () => {
    syncEdgePresentation()
    const edge = edges.value.find((item) => item.id === props.selectedEdgeId)
    const relationType = edge?.data?.relationType as CreativeRelationType | undefined
    if (relationType) selectedRelationType.value = relationType
  },
  { immediate: true },
)

watch(
  () => props.graphVersion,
  () => {
    /* 右侧详情编辑或后端恢复后，AppShell 会把新的权威快照推回画布。 */
    nodes.value = props.initialNodes.map((node) =>
      cloneNode(node, props.selectedNodeId, new Set(props.highlightedNodeIds)),
    )
    edges.value = props.initialEdges.map((edge) =>
      normalizeEdge(edge, new Set(props.highlightedEdgeIds), edge.id === (props.selectedEdgeId ?? '')),
    )
  },
)

watch(
  () => [props.highlightedNodeIds.join(','), props.highlightedEdgeIds.join(',')],
  () => {
    const highlightedNodes = new Set(props.highlightedNodeIds)
    const highlightedEdges = new Set(props.highlightedEdgeIds)

    for (const node of nodes.value) {
      const next = highlightedNodes.has(node.id) ? 'is-highlighted' : ''
      if (node.class !== next) {
        node.class = next
      }
    }

    edges.value.forEach((edge) => {
      const normalized = normalizeEdge(
        edge,
        highlightedEdges,
        edge.id === (props.selectedEdgeId ?? ''),
      )
      edge.class = normalized.class
      edge.selected = normalized.selected
      const internal = findEdge(edge.id)
      if (internal) {
        internal.class = normalized.class
        internal.selected = Boolean(normalized.selected)
      }
    })
  },
)

watch(
  () => props.createNodeRequest?.nonce,
  () => {
    if (!props.createNodeRequest) return
    handleCreateNode(props.createNodeRequest.type)
  },
)

watch(
  () => props.focusNodeRequest?.nonce,
  () => {
    if (props.focusNodeRequest) selectNode(props.focusNodeRequest.id, true)
  },
)
</script>

<template>
  <section class="canvas-workspace">
    <!-- 画布工具栏 -->
    <header class="canvas-toolbar">
      <div class="toolbar-group toolbar-group--create">
        <slot name="toolbar-leading" />
      </div>

      <div class="toolbar-group toolbar-group--end">
        <div class="toolbar-group toolbar-group--status">
          <slot name="toolbar-trailing" />
        </div>

        <div class="toolbar-sep" aria-hidden="true" />

        <div class="toolbar-group toolbar-group--view canvas-actions" aria-label="画布视图">
          <button type="button" class="toolbar-btn toolbar-btn--icon" title="放大" @click="handleZoomIn">+</button>
          <button type="button" class="toolbar-btn toolbar-btn--icon" title="缩小" @click="handleZoomOut">−</button>
          <button type="button" class="toolbar-btn" title="按关系自动整理成树状图" @click="handleAutoArrange">树状整理</button>
          <button type="button" class="toolbar-btn" @click="handleFitView">适应</button>
          <button type="button" class="toolbar-btn toolbar-btn--danger" @click="handleClearCanvas">清空</button>
        </div>
      </div>
    </header>

    <div
      ref="flowShell"
      class="flow-shell"
      :class="{ 'is-middle-pan-ready': isMiddleMouseDown }"
    >
      <!-- v-model 绑定本地 refs；拖拽、连线、标签恢复后，会向 AppShell 上抛可保存快照。 -->
      <VueFlow
        :id="FLOW_ID"
        v-model:nodes="nodes"
        v-model:edges="edges"
        class="creative-flow"
        :default-viewport="{ x: 40, y: 36, zoom: 0.82 }"
        :min-zoom="0.35"
        :max-zoom="1.6"
        :nodes-connectable="true"
        :nodes-draggable="true"
        :elements-selectable="true"
        :connection-mode="ConnectionMode.Loose"
        :connect-on-click="false"
        :connection-radius="24"
        :edges-updatable="true"
        :fit-view-on-init="true"
        :pan-on-drag="[1]"
        :selection-on-drag="true"
        :selection-key-code="true"
        :multi-selection-key-code="null"
        :selection-mode="SelectionMode.Partial"
        @connect="handleConnect"
        @edge-update="handleEdgeUpdate"
        @node-click="handleNodeClick"
        @edge-click="handleEdgeClick"
        @node-drag-stop="handleNodeDragStop"
        @selection-change="handleSelectionChange"
      >
        <template #node-character="nodeProps">
          <CharacterNode v-bind="nodeProps" />
        </template>

        <template #node-worldbuilding="nodeProps">
          <WorldNode v-bind="nodeProps" />
        </template>

        <template #node-plot="nodeProps">
          <PlotNode v-bind="nodeProps" />
        </template>

        <template #node-idea="nodeProps">
          <IdeaNode v-bind="nodeProps" />
        </template>

        <template #node-research="nodeProps">
          <ResearchNode v-bind="nodeProps" />
        </template>

        <template #node-structure="nodeProps">
          <StructureNode v-bind="nodeProps" />
        </template>

        <template #edge-bezier="edgeProps">
          <CreativeBezierEdge v-bind="edgeProps" />
        </template>
      </VueFlow>

      <!-- 交互提示，轻量放在画布左下角。 -->
      <ul class="canvas-hint" aria-hidden="true">
        <li><span class="canvas-hint__key">选择</span><span>左键点击</span></li>
        <li><span class="canvas-hint__key">连线</span><span>点击 / 右键</span></li>
        <li><span class="canvas-hint__key">菜单</span><span>右键</span></li>
        <li><span class="canvas-hint__key">平移</span><span>中键拖动</span></li>
      </ul>
    </div>

    <EdgeRelationMenu
      :show="edgeRelationMenu.show"
      :x="edgeRelationMenu.x"
      :y="edgeRelationMenu.y"
      :current-type="edgeRelationMenu.relationType"
      @select="handleEdgeRelationSelect"
      @close="closeEdgeRelationMenu"
    />

    <CanvasContextMenu
      :show="contextMenu.show"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :menu-type="contextMenu.type"
      :create-types="blankCreateTypes"
      :edge-label="contextMenu.edgeLabel"
      @create="handleMenuCreate"
      @edit="handleMenuEdit"
      @duplicate="handleMenuDuplicate"
      @remove="handleMenuRemoveClick"
      @quote="handleMenuQuote"
      @change-relation="handleMenuEdgeChangeRelation"
      @close="closeContextMenu"
    />
  </section>
</template>

<style scoped src="./CanvasWorkspace.scoped.css"></style>
