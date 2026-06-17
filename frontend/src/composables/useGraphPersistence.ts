import { computed, ref } from 'vue'
import type { GraphDto, IndexingStatusDto, SaveGraphDto } from '../api/graphApi'
import { loadDefaultGraph, saveProjectGraph } from '../api/graphApi'
import type { CreativeFlowEdge, CreativeFlowNode, CreativeGraphSnapshot } from '../types/node'
import { graphDtoToSnapshot, snapshotToSaveDto } from '../utils/graphTransform'

const CANVAS_AUTO_SAVE_DELAY_MS = 1000

/**
 * 可注入的加载 / 保存策略（first_revision 第 3 阶段）。
 *
 * 默认使用 default-project 维度（AppShell 原本的单画布行为）；三个工作区视图会注入
 * 子图维度的 loadSubgraph / saveSubgraph，从而复用这里的快照和防抖保存逻辑。
 */
export interface GraphPersistenceLoaders {
  load: () => Promise<GraphDto>
  save: (dto: SaveGraphDto) => Promise<GraphDto>
}

/**
 * 维护工作区图谱的加载、保存和自动保存语义。
 *
 * 任何真正修改 graphSnapshot 的入口都经过 setGraphSnapshot；自动保存使用单个防抖队列，
 * 避免并发覆盖。暂存项接受后会调用 clearAutoSave 丢弃过期的待保存快照，
 * 防止旧快照覆盖后端刚持久化的新节点 / 新边。
 */
export function useGraphPersistence(
  applyIndexingStatus: (indexing?: IndexingStatusDto) => void,
  loaders?: GraphPersistenceLoaders,
) {
  const projectId = ref('')
  const projectName = ref('正在加载项目…')
  const graphSnapshot = ref<CreativeGraphSnapshot>({ nodes: [], edges: [] })
  const graphNodes = ref<CreativeFlowNode[]>([])
  const graphEdges = ref<CreativeFlowEdge[]>([])
  const graphVersion = ref(0)
  const isGraphReady = ref(false)
  const isSaving = ref(false)
  const saveState = ref('加载中…')

  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

  const MAX_HISTORY = 50
  const undoStack = ref<CreativeGraphSnapshot[]>([])
  const redoStack = ref<CreativeGraphSnapshot[]>([])
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function cloneSnapshot(s: CreativeGraphSnapshot): CreativeGraphSnapshot {
    return JSON.parse(JSON.stringify({ nodes: s.nodes, edges: s.edges }))
  }

  /** 把当前快照记录为撤销检查点；应在应用用户编辑前调用。 */
  function recordHistory() {
    undoStack.value.push(cloneSnapshot(graphSnapshot.value))
    if (undoStack.value.length > MAX_HISTORY) undoStack.value.shift()
    redoStack.value = []
  }

  function undo() {
    const prev = undoStack.value.pop()
    if (!prev) return
    redoStack.value.push(cloneSnapshot(graphSnapshot.value))
    setGraphSnapshot(prev, true)
    scheduleAutoSave(CANVAS_AUTO_SAVE_DELAY_MS)
  }

  function redo() {
    const next = redoStack.value.pop()
    if (!next) return
    undoStack.value.push(cloneSnapshot(graphSnapshot.value))
    setGraphSnapshot(next, true)
    scheduleAutoSave(CANVAS_AUTO_SAVE_DELAY_MS)
  }

  function setGraphSnapshot(snapshot: CreativeGraphSnapshot, shouldPushToCanvas = false) {
    graphSnapshot.value = snapshot
    graphNodes.value = snapshot.nodes
    graphEdges.value = snapshot.edges
    if (shouldPushToCanvas) {
      graphVersion.value += 1
    }
  }

  async function persistGraph(refreshFromResponse = false) {
    if (!projectId.value) {
      return
    }
    if (isSaving.value) {
      if (!refreshFromResponse) {
        scheduleAutoSave()
      }
      return
    }
    try {
      isSaving.value = true
      saveState.value = '保存中…'
      const saveDto = snapshotToSaveDto(graphSnapshot.value)
      const savedGraph = loaders
        ? await loaders.save(saveDto)
        : await saveProjectGraph(projectId.value, saveDto)
      if (refreshFromResponse) {
        setGraphSnapshot(graphDtoToSnapshot(savedGraph), true)
      }
      applyIndexingStatus(savedGraph.indexing)
      saveState.value = `已保存 · ${new Date().toLocaleTimeString()}`
    } catch (error) {
      saveState.value = error instanceof Error ? `保存失败: ${error.message}` : '保存失败'
    } finally {
      isSaving.value = false
    }
  }

  function scheduleAutoSave(delayMs = CANVAS_AUTO_SAVE_DELAY_MS) {
    if (!isGraphReady.value || !projectId.value) {
      return
    }
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
    }
    saveState.value = '有未保存修改'
    autoSaveTimer = setTimeout(() => {
      void persistGraph(false)
    }, delayMs)
  }

  function clearAutoSave() {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
  }

  async function loadGraph(): Promise<{ initialNodeId: string }> {
    try {
      saveState.value = '加载中…'
      const graph = loaders ? await loaders.load() : await loadDefaultGraph()
      const snapshot = graphDtoToSnapshot(graph)
      projectId.value = graph.project.id
      projectName.value = graph.project.name
      setGraphSnapshot(snapshot, true)
      undoStack.value = []
      redoStack.value = []
      isGraphReady.value = true
      saveState.value = '已加载'
      applyIndexingStatus(graph.indexing)
      return { initialNodeId: snapshot.nodes[0]?.id ?? '' }
    } catch (error) {
      isGraphReady.value = false
      saveState.value =
        error instanceof Error ? `加载失败: ${error.message}` : '加载失败'
      return { initialNodeId: '' }
    }
  }

  function handleGraphChanged(snapshot: CreativeGraphSnapshot) {
    recordHistory()
    setGraphSnapshot(snapshot)
    scheduleAutoSave(CANVAS_AUTO_SAVE_DELAY_MS)
  }

  async function handleSaveGraph() {
    clearAutoSave()
    await persistGraph(true)
  }

  return {
    projectId,
    projectName,
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
    handleSaveGraph,
    recordHistory,
    undo,
    redo,
    canUndo,
    canRedo,
  }
}
