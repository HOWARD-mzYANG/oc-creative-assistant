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

// 工作区保存后，防抖 30 秒再触发 seed 重建（first_revision 第 5 阶段触发条件之一）。
const SEED_REBUILD_DEBOUNCE_MS = 30000
const HIGHLIGHT_DURATION_MS = 2600

/**
 * 单个子图画布（first_revision 第 3 阶段）。
 *
 * 复用现有 CanvasWorkspace（Vue Flow）+ 详情编辑 + useGraphPersistence/useGraphMutations，
 * 只在子图层注入 load/save。这里不改变这些组件 / composable 的内部逻辑，
 * 只负责组合它们并绑定 graphId。
 */
const props = defineProps<{
  graphId: string
  /** 当前视图允许创建的节点类型（故事视图只创建 plot，世界观视图只创建 worldbuilding）。 */
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

/** 成功保存后安排一次 seed 重建；连续保存时只保留最后一次。 */
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

/** 说明 tryFocusPending 的局部业务逻辑。 */
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

// 详情编辑已移出右栏（second_revision 变更 B）：右栏现在是 AI 输出区，
// 节点详情通过中央 NodeDetailView（W3）处理，标题 / 摘要使用行内编辑（W2）。
// 这里仅保留键盘删除。
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
  idea: '想法',
  research: '资料',
  structure: '结构',
}
const createButtons = computed(() =>
  props.createTypes.map((type) => ({
    type,
    label: TYPE_LABEL_EN[type] ?? nodeTypeOptions.find((o) => o.type === type)?.label ?? type,
  })),
)

/** 选择目标对象并同步当前状态。 */
function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId
  selectedEdgeId.value = ''
}

/** 选择目标对象并同步当前状态。 */
function selectEdge(edgeId: string) {
  selectedEdgeId.value = edgeId
  selectedNodeId.value = ''
}

/** 说明 requestCreateNode 的局部业务逻辑。 */
function requestCreateNode(nodeType: CreativeNodeType) {
  createNodeRequest.value = { type: nodeType, nonce: Date.now() }
}

/** 重新加载当前视图所需的数据。 */
async function reload() {
  clearAutoSave()
  const { initialNodeId } = await loadGraph()
  selectedNodeId.value = initialNodeId
  selectedEdgeId.value = ''
  tryFocusPending()
}

/** 处理对应的用户交互或组件事件。 */
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
  centerStage.returnToCanvas() // 进入画布视图时重置，避免上一个视图遗留详情状态。
  void reload()
})

// 从节点详情返回画布时重新加载，确保详情页编辑能反映到画布。
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

// 在同一个 WorkspaceShell 内切换 plot↔world 时 graphId 会变化，需要重新加载。
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
            + 新建 {{ button.label }}
          </button>
        </template>
        <template #toolbar-trailing>
          <span class="toolbar-save-status">
            <span
              class="toolbar-save-dot"
              :class="{ 'is-saving': isSaving, 'is-error': saveState.includes('保存失败') || saveState.includes('failed') }"
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
