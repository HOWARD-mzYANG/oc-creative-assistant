<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadSubgraph, saveSubgraph } from '../../api/graphApi'
import { rebuildProjectSeed } from '../../api/projectApi'
import { useGraphMutations } from '../../composables/useGraphMutations'
import { useGraphPersistence } from '../../composables/useGraphPersistence'
import { useIndexingStatus } from '../../composables/useIndexingStatus'
import {
  injectWorkspaceGraphRefresh,
  injectWorkspaceSelectedNodeIds,
} from '../../composables/useWorkspaceChatContext'
import { useProjectStore } from '../../stores/useProjectStore'
import { useCenterStageStore } from '../../stores/useCenterStageStore'
import { useNodeNavStore } from '../../stores/useNodeNavStore'
import { nodeTypeOptions } from '../../utils/nodeFactory'
import type { CreativeNodeType } from '../../types/node'
import CanvasWorkspace from '../canvas/CanvasWorkspace.vue'
import NodeDetailView from './NodeDetailView.vue'

// After a workspace save, debounce 30s before triggering a seed rebuild (one of the first_revision phase 5 triggers).
const SEED_REBUILD_DEBOUNCE_MS = 30000
const HIGHLIGHT_DURATION_MS = 2600

/**
 * Single sub-graph canvas (first_revision phase 3).
 *
 * Reuses the existing CanvasWorkspace (Vue Flow) + AgentSidebar (node/edge detail
 * editing) + useGraphPersistence/useGraphMutations, only injecting load/save at the
 * sub-graph level. It does not change the internal logic of these
 * components/composables, just composes them and binds to graphId.
 */
const props = defineProps<{
  graphId: string
  /** Node types this view allows creating (the story view only creates plot, worldbuilding only creates worldbuilding). */
  createTypes: CreativeNodeType[]
}>()

const { applyIndexingStatus } = useIndexingStatus()
const projectStore = useProjectStore()
const centerStage = useCenterStageStore()
const nodeNav = useNodeNavStore()
const workspaceSelectedNodeIds = injectWorkspaceSelectedNodeIds()
const graphRefresh = injectWorkspaceGraphRefresh()

let seedTimer: ReturnType<typeof setTimeout> | null = null
let highlightClearTimer: ReturnType<typeof setTimeout> | null = null

/** Schedule one seed rebuild after a successful save; consecutive saves keep only the last. */
function scheduleSeedRebuild() {
  const projectId = projectStore.detail?.id
  if (!projectId) return
  if (seedTimer) clearTimeout(seedTimer)
  seedTimer = setTimeout(() => {
    void rebuildProjectSeed(projectId)
      .then(() => projectStore.loadProject(projectId, true))
      .catch(() => {})
  }, SEED_REBUILD_DEBOUNCE_MS)
}

const {
  graphSnapshot,
  graphNodes,
  graphEdges,
  graphVersion,
  isSaving,
  saveState,
  setGraphSnapshot,
  scheduleAutoSave,
  clearAutoSave,
  loadGraph,
  handleGraphChanged,
  recordHistory,
  undo,
  redo,
} = useGraphPersistence(applyIndexingStatus, {
  load: () => loadSubgraph(props.graphId),
  save: async (dto) => {
    const saved = await saveSubgraph(props.graphId, dto)
    scheduleSeedRebuild()
    return saved
  },
})

const selectedNodeId = ref('')
const selectedEdgeId = ref('')
const createNodeRequest = ref<{ type: CreativeNodeType; nonce: number } | null>(null)
const focusNodeRequest = ref<{ id: string; nonce: number } | null>(null)

function tryFocusPending() {
  const pendingId = nodeNav.pendingNodeId
  if (!pendingId) return
  if (!graphSnapshot.value.nodes.some((n) => n.id === pendingId)) return
  nodeNav.consume()
  selectedNodeId.value = pendingId
  selectedEdgeId.value = ''
  focusNodeRequest.value = { id: pendingId, nonce: Date.now() }
}
const highlightedNodeIds = ref<string[]>([])
const highlightedEdgeIds = ref<string[]>([])

// Detail editing has moved out of the right column (second_revision change B): the right
// column is now the AI output area, node detail goes through the center NodeDetailView (W3),
// and title/summary use inline edit (W2). Only keyboard deletion is kept here.
const { handleGlobalKeydown } = useGraphMutations({
  graphSnapshot,
  selectedNodeId,
  selectedEdgeId,
  setGraphSnapshot,
  scheduleAutoSave,
  recordHistory,
  undo,
  redo,
})

const TYPE_LABEL_EN: Record<string, string> = {
  character: '角色',
  worldbuilding: '世界观',
  plot: '故事节点',
  idea: 'Idea',
  research: '资料',
  structure: '结构',
}
const createButtons = computed(() =>
  props.createTypes.map((type) => ({
    type,
    label: TYPE_LABEL_EN[type] ?? nodeTypeOptions.find((o) => o.type === type)?.label ?? type,
  })),
)

function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId
  selectedEdgeId.value = ''
}

function selectEdge(edgeId: string) {
  selectedEdgeId.value = edgeId
  selectedNodeId.value = ''
}

function requestCreateNode(nodeType: CreativeNodeType) {
  createNodeRequest.value = { type: nodeType, nonce: Date.now() }
}

async function reload() {
  clearAutoSave()
  const { initialNodeId } = await loadGraph()
  selectedNodeId.value = initialNodeId
  selectedEdgeId.value = ''
  tryFocusPending()
}

async function handleGraphRefreshNeeded() {
  clearAutoSave()

  const prevNodeIds = new Set(graphSnapshot.value.nodes.map((node) => node.id))
  const prevEdgeIds = new Set(graphSnapshot.value.edges.map((edge) => edge.id))

  await reload()

  const newNodeIds = graphSnapshot.value.nodes
    .map((node) => node.id)
    .filter((id) => !prevNodeIds.has(id))
  const newEdgeIds = graphSnapshot.value.edges
    .map((edge) => edge.id)
    .filter((id) => !prevEdgeIds.has(id))

  if (newNodeIds.length === 0 && newEdgeIds.length === 0) {
    return
  }

  highlightedNodeIds.value = newNodeIds
  highlightedEdgeIds.value = newEdgeIds

  if (highlightClearTimer) {
    clearTimeout(highlightClearTimer)
  }
  highlightClearTimer = setTimeout(() => {
    highlightedNodeIds.value = []
    highlightedEdgeIds.value = []
  }, HIGHLIGHT_DURATION_MS)
}

watch(selectedNodeId, (nodeId) => {
  workspaceSelectedNodeIds.value = nodeId ? [nodeId] : []
})

watch(() => nodeNav.pendingNodeId, () => tryFocusPending())

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown, true)
  graphRefresh?.register(handleGraphRefreshNeeded)
  centerStage.returnToCanvas() // Reset when entering the canvas view, to avoid leftover detail state from the previous view
  void reload()
})

// Reload when returning from node detail to the canvas, to ensure detail-page edits are reflected on the canvas.
watch(
  () => centerStage.mode,
  (mode, old) => {
    if (mode === 'canvas' && old === 'detail') void reload()
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown, true)
  graphRefresh?.register(async () => {})
  clearAutoSave()
  if (seedTimer) clearTimeout(seedTimer)
  if (highlightClearTimer) clearTimeout(highlightClearTimer)
})

// When switching plot↔world within the same WorkspaceShell, graphId changes and a reload is needed.
watch(
  () => props.graphId,
  () => {
    centerStage.returnToCanvas()
    void reload()
  },
)
</script>

<template>
  <transition name="stage" mode="out-in" class="subgraph-stage">
  <NodeDetailView
    v-if="centerStage.mode === 'detail' && centerStage.detailNodeId"
    :node-id="centerStage.detailNodeId"
    @return="centerStage.returnToCanvas()"
  />
  <div v-else class="subgraph-canvas">
    <div class="subgraph-canvas__body">
      <CanvasWorkspace
        :selected-node-id="selectedNodeId"
        :selected-edge-id="selectedEdgeId"
        :initial-nodes="graphNodes"
        :initial-edges="graphEdges"
        :graph-version="graphVersion"
        :create-node-request="createNodeRequest"
        :focus-node-request="focusNodeRequest"
        :highlighted-node-ids="highlightedNodeIds"
        :highlighted-edge-ids="highlightedEdgeIds"
        :create-types="createTypes"
        @node-selected="selectNode"
        @edge-selected="selectEdge"
        @graph-changed="handleGraphChanged"
      >
        <template #toolbar-leading>
          <button
            v-for="button in createButtons"
            :key="button.type"
            type="button"
            class="toolbar-create-btn"
            @click="requestCreateNode(button.type)"
          >
            + New {{ button.label }}
          </button>
        </template>
        <template #toolbar-trailing>
          <span class="toolbar-save-status">
            <span
              class="toolbar-save-dot"
              :class="{ 'is-saving': isSaving, 'is-error': saveState.includes('failed') }"
            ></span>
            {{ isSaving ? '保存中…' : saveState }}
          </span>
        </template>
      </CanvasWorkspace>
    </div>
  </div>
  </transition>
</template>

<style scoped>
.subgraph-stage {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
}
.subgraph-canvas {
  height: 100%;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}
.subgraph-canvas__body {
  min-height: 0;
  display: grid;
}
.toolbar-save-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.toolbar-save-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  transition: background 0.3s ease;
}
.toolbar-save-dot.is-saving {
  background: #f59e0b;
}
.toolbar-save-dot.is-error {
  background: #dc2626;
}
.toolbar-io-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  background: #fff;
  color: var(--text);
  cursor: pointer;
}
.toolbar-io-btn:hover {
  border-color: var(--accent);
  color: var(--accent-deep);
}
</style>
