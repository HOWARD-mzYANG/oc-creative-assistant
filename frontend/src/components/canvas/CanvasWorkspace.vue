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
 * Creative canvas component.
 *
 * This component handles Vue Flow runtime interactions, node rendering, and
 * synchronization between external props (graphVersion / createNodeRequest /
 * highlightedXxxIds) and the local nodes/edges; the core operations for
 * adding/removing/editing graph content live in useCanvasGraph, while pure
 * functions like relation types / node clone live in utils/canvasRelations.
 */
const props = defineProps<{
  selectedNodeId: string
  selectedEdgeId?: string
  initialNodes: CreativeFlowNode[]
  initialEdges: CreativeFlowEdge[]
  graphVersion: number
  createNodeRequest: { type: CreativeNodeType; nonce: number } | null
  focusNodeRequest?: { id: string; nonce: number } | null
  /* IDs that "just appeared", computed by AppShell as a diff after staging is accepted; cleared once the animation finishes */
  highlightedNodeIds: string[]
  highlightedEdgeIds: string[]
  /* Node types that can be created on right-clicking blank space; SubgraphCanvas passes them per sub-graph, defaults to all types if not provided */
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

function onFlowShellMouseDown(event: MouseEvent) {
  if (event.button !== 1) return
  event.preventDefault()
  isMiddleMouseDown.value = true
}

function onFlowShellMouseUp(event: MouseEvent) {
  if (event.button === 1) {
    isMiddleMouseDown.value = false
  }
}

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

/* A fixed flow id ensures toolbar actions bind to the current canvas instance, instead of being hijacked by other Vue Flow instances on the page */
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

function closeEdgeRelationMenu() {
  edgeRelationMenu.value.show = false
}

function closeContextMenu() {
  contextMenu.value.show = false
}

function pointerFromEvent(event: MouseEvent | TouchEvent): { x: number; y: number } {
  if (event instanceof MouseEvent) {
    return { x: event.clientX, y: event.clientY }
  }
  const touch = event.touches[0] ?? event.changedTouches[0]
  return { x: touch?.clientX ?? 0, y: touch?.clientY ?? 0 }
}

/** Keep the menu on-screen; coordinates are viewport-based (Teleport to body). */
function clampMenuPosition(x: number, y: number): { x: number; y: number } {
  const pad = 8
  const maxW = 200
  const maxH = 260
  return {
    x: Math.max(pad, Math.min(x, window.innerWidth - maxW - pad)),
    y: Math.max(pad, Math.min(y, window.innerHeight - maxH - pad)),
  }
}

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

// Double-click a node -> open node details (center NodeDetailView), carrying the current data snapshot.
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

function handleEdgeRelationSelect(relationType: CreativeRelationType) {
  if (!edgeRelationMenu.value.edgeId) return
  updateEdgeRelation(edgeRelationMenu.value.edgeId, relationType)
  closeEdgeRelationMenu()
}

function nodeRef(nodeId: string) {
  return nodes.value.find((node) => node.id === nodeId)
}

function handleMenuCreate(type: CreativeNodeType) {
  const pos = screenToFlowCoordinate({ x: contextMenu.value.x, y: contextMenu.value.y })
  handleCreateNode(type, { x: pos.x, y: pos.y })
  closeContextMenu()
}

function handleMenuEdit() {
  if (contextMenu.value.nodeId) centerStage.openDetail(contextMenu.value.nodeId)
  closeContextMenu()
}

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
        title: `${src.data.title} copy`,
        content: src.data.content,
      })
    }
  }
  closeContextMenu()
}

function handleMenuRemove() {
  if (contextMenu.value.nodeId) removeNode(contextMenu.value.nodeId)
  closeContextMenu()
}

function handleMenuRemoveClick() {
  if (contextMenu.value.type === 'edge') {
    handleMenuEdgeRemove()
  } else {
    handleMenuRemove()
  }
}

function handleMenuEdgeRemove() {
  if (contextMenu.value.edgeId) removeEdge(contextMenu.value.edgeId)
  closeContextMenu()
}

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

function quoteNodes(refs: { id: string; type: string; title: string }[]) {
  if (refs.length) composer.addReferences(refs)
}

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

/** Ctrl/Cmd+C: copy the currently multi-selected nodes as reference cards into the bottom composer. */
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
 * Update the selected state of canvas nodes, and focus the viewport as needed.
 *
 * The visual selection marker is maintained by this component; the business-side
 * "current selection" is pushed back by AppShell via props.selectedNodeId,
 * forming a one-way data flow.
 *
 * Args:
 *   nodeId: ID of the node to select.
 *   shouldFocus: whether to move the viewport near that node.
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

/** Bubble Vue Flow node click events up to AppShell to maintain the global selection. */
function handleNodeClick(event: NodeMouseEvent) {
  skipNextFocus.value = true
  emit('nodeSelected', event.node.id)
}

/** Sync primary selection after box-select; keep isActive aligned with Vue Flow selection. */
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

function syncEdgePresentation(highlighted = new Set(props.highlightedEdgeIds)) {
  const selectedId = props.selectedEdgeId ?? ''
  edges.value = edges.value.map((edge) =>
    normalizeEdge(edge, highlighted, edge.id === selectedId),
  )
}

/** Bubble Vue Flow edge click events up to AppShell to maintain the global selection. */
function handleEdgeClick(event: { edge: Edge }) {
  skipNextFocus.value = true
  emit('edgeSelected', event.edge.id)
  syncEdgePresentation()
}

/** Fit the viewport to the full graph extent, making it easier to regain the overall structure as nodes grow. */
function handleFitView() {
  void fitView({ padding: 0.2, duration: 260 })
}

function handleZoomIn() {
  void zoomIn({ duration: 180 })
}

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
    /* After detail edits on the right or a backend restore, AppShell pushes the new authoritative snapshot back to the canvas */
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
    <!-- Canvas toolbar -->
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
      <!-- v-model binds local refs; after drag, connect, and label restore, events bubble a savable snapshot up to AppShell. -->
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

      <!-- Interaction hint, lightly penciled into the bottom-left corner of the canvas -->
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
