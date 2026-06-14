<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { loadSubgraph, saveSubgraph } from '../../../api/graphApi'
import { rebuildProjectSeed } from '../../../api/projectApi'
import { useGraphPersistence } from '../../../composables/useGraphPersistence'
import { useNodeFieldsCache } from '../../../composables/useNodeFieldsCache'
import { useIndexingStatus } from '../../../composables/useIndexingStatus'
import {
  injectWorkspaceGraphRefresh,
} from '../../../composables/useWorkspaceChatContext'
import { useProjectStore } from '../../../stores/useProjectStore'
import { useWorldViewStore } from '../../../stores/useWorldViewStore'
import { useNodeNavStore } from '../../../stores/useNodeNavStore'
import type { CreativeFlowNode } from '../../../types/node'
import { createCreativeNode } from '../../../utils/nodeFactory'
import {
  buildWorldForest,
  buildWorldSaveSnapshot,
  inferWorldHierarchyFromEdges,
  moveWorldNode,
  nextWorldSortOrder,
  type WorldMoveTarget,
} from '../../../utils/worldHierarchy'
import WorldFolderTree from './WorldFolderTree.vue'
import WorldNotePanel from './WorldNotePanel.vue'
import WorldTreeCanvas from './WorldTreeCanvas.vue'

const SEED_REBUILD_DEBOUNCE_MS = 5000
const WORLD_GRAPH_SAVE_DELAY_MS = 400

const props = defineProps<{ graphId: string }>()

const { applyIndexingStatus } = useIndexingStatus()
const projectStore = useProjectStore()
const worldViewStore = useWorldViewStore()
const nodeNav = useNodeNavStore()
const { mode: viewMode } = storeToRefs(worldViewStore)
const graphRefresh = injectWorkspaceGraphRefresh()
const fieldsCache = useNodeFieldsCache()
const selectedId = ref('')
let createCount = 0
let seedTimer: ReturnType<typeof setTimeout> | null = null

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
  setGraphSnapshot,
  scheduleAutoSave,
  clearAutoSave,
  loadGraph,
} = useGraphPersistence(applyIndexingStatus, {
  load: () => loadSubgraph(props.graphId),
  save: async (dto) => {
    const saved = await saveSubgraph(props.graphId, dto)
    scheduleSeedRebuild()
    return saved
  },
})

const nodes = computed(() => graphSnapshot.value.nodes)

const forest = computed(() => buildWorldForest(nodes.value))

const selectedNode = computed(
  () => nodes.value.find((node) => node.id === selectedId.value) ?? null,
)

function commitSnapshot(nextNodes: CreativeFlowNode[]) {
  setGraphSnapshot(buildWorldSaveSnapshot(nextNodes))
  scheduleAutoSave(WORLD_GRAPH_SAVE_DELAY_MS)
}

function updateNode(nodeId: string, patch: Partial<CreativeFlowNode['data']>) {
  commitSnapshot(
    nodes.value.map((node) =>
      node.id === nodeId ? { ...node, data: { ...node.data, ...patch } } : node,
    ),
  )
}

function collectDescendantIds(rootId: string): Set<string> {
  const ids = new Set<string>([rootId])
  let expanded = true
  while (expanded) {
    expanded = false
    for (const node of nodes.value) {
      const parentId = node.data.parentId
      if (parentId && ids.has(parentId) && !ids.has(node.id)) {
        ids.add(node.id)
        expanded = true
      }
    }
  }
  return ids
}

function createNote(parentId: string | null) {
  createCount += 1
  const node = createCreativeNode('worldbuilding', createCount, { x: 0, y: 0 })
  node.data.parentId = parentId
  node.data.sortOrder = nextWorldSortOrder(nodes.value, parentId)
  commitSnapshot([...nodes.value, node])
  selectedId.value = node.id
}

function moveNote(draggedId: string, target: WorldMoveTarget) {
  const nextNodes = moveWorldNode(nodes.value, draggedId, target)
  if (!nextNodes) return
  commitSnapshot(nextNodes)
  selectedId.value = draggedId
}

function deleteNote(nodeId: string) {
  const node = nodes.value.find((item) => item.id === nodeId)
  if (!node) return
  const confirmed = window.confirm(
    `删除“${node.data.title}”及其嵌套笔记吗？`,
  )
  if (!confirmed) return

  const removeIds = collectDescendantIds(nodeId)
  const nextNodes = nodes.value.filter((item) => !removeIds.has(item.id))
  if (selectedId.value && removeIds.has(selectedId.value)) {
    selectedId.value = nextNodes[0]?.id ?? ''
  }
  commitSnapshot(nextNodes)
}

function deleteSelectedNote() {
  if (!selectedId.value) return
  deleteNote(selectedId.value)
}

function tryFocusPending() {
  const pendingId = nodeNav.pendingNodeId
  if (!pendingId) return
  if (!nodes.value.some((n) => n.id === pendingId)) return
  nodeNav.consume()
  selectedId.value = pendingId
  worldViewStore.setMode('notes')
}

async function reload() {
  clearAutoSave()
  await loadGraph()
  const migrated = inferWorldHierarchyFromEdges(graphSnapshot.value)
  if (
    migrated.nodes !== graphSnapshot.value.nodes ||
    migrated.edges.length !== graphSnapshot.value.edges.length
  ) {
    setGraphSnapshot(migrated, true)
    scheduleAutoSave()
  }
  if (!selectedId.value || !nodes.value.some((node) => node.id === selectedId.value)) {
    selectedId.value = nodes.value[0]?.id ?? ''
  }
  tryFocusPending()

  const projectId = projectStore.detail?.id
  if (projectId && nodes.value.length > 0) {
    void fieldsCache.prefetch(
      projectId,
      nodes.value.map((node) => node.id),
    )
  }
}

async function handleGraphRefreshNeeded() {
  clearAutoSave()
  await reload()
}

onMounted(() => {
  graphRefresh?.register(handleGraphRefreshNeeded)
  void reload()
})

onBeforeUnmount(() => {
  graphRefresh?.register(async () => {})
  clearAutoSave()
  if (seedTimer) clearTimeout(seedTimer)
})

watch(
  () => props.graphId,
  () => {
    selectedId.value = ''
    void reload()
  },
)

watch(() => nodeNav.pendingNodeId, () => tryFocusPending())
</script>

<template>
  <div class="world-notes-workspace">
    <div class="world-notes-workspace__main">
      <div v-show="viewMode === 'canvas'" class="world-notes-workspace__canvas">
        <WorldTreeCanvas
          :nodes="graphSnapshot.nodes"
          :selected-id="selectedId"
          :active="viewMode === 'canvas'"
          @select="(id) => { selectedId = id; worldViewStore.setMode('notes') }"
        />
      </div>

      <div v-show="viewMode === 'notes'" class="world-notes-workspace__notes">
        <aside class="world-notes-workspace__sidebar">
          <WorldFolderTree
            :forest="forest"
            :selected-id="selectedId"
            @select="selectedId = $event"
            @add-child="createNote"
            @add-root="createNote(null)"
            @delete="deleteNote"
            @move="moveNote"
          />
        </aside>
        <main class="world-notes-workspace__editor">
          <WorldNotePanel
            :node="selectedNode"
            :project-id="projectStore.detail?.id ?? ''"
            @update="(patch) => selectedId && updateNode(selectedId, patch)"
            @delete="deleteSelectedNote"
          />
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.world-notes-workspace {
  height: 100%;
  min-height: 0;
  background: var(--panel);
}

.world-notes-workspace__main {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
}

.world-notes-workspace__main > * {
  grid-row: 1;
  grid-column: 1;
  min-height: 0;
}

.world-notes-workspace__notes,
.world-notes-workspace__canvas {
  height: 100%;
}

.world-notes-workspace__notes {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
}

.world-notes-workspace__sidebar {
  min-height: 0;
  overflow: auto;
  border-right: 1px solid var(--border);
  padding: 10px 8px;
  background:
    radial-gradient(circle at 0% 0%, rgba(233, 130, 74, 0.08), transparent 55%),
    var(--panel);
}

.world-notes-workspace__editor {
  min-height: 0;
  overflow: hidden;
}
</style>
