import { ref, type Ref } from 'vue'
import { addEdge, updateEdge } from '@vue-flow/core'
import type { Connection, Edge } from '@vue-flow/core'
import type {
  CreativeFlowEdge,
  CreativeFlowNode,
  CreativeGraphSnapshot,
  CreativeNodeType,
  CreativeRelationType,
} from '../types/node'
import { arrangeNodesAsHierarchy, findFreeNodePosition } from '../utils/canvasLayout'
import { createCreativeNode } from '../utils/nodeFactory'
import {
  DEFAULT_SOURCE_HANDLE,
  DEFAULT_TARGET_HANDLE,
  getRelationLabel,
  normalizeEdge,
} from '../utils/canvasRelations'

interface Options {
  nodes: Ref<CreativeFlowNode[]>
  edges: Ref<CreativeFlowEdge[]>
  flowShell: Ref<HTMLElement | null>
  selectedRelationType: Ref<CreativeRelationType>
  getViewport: () => { x: number; y: number; zoom: number }
  onGraphChanged: (snapshot: CreativeGraphSnapshot) => void
  onNodeAdded: (node: CreativeFlowNode) => void
  onNodeSelected: (id: string) => void
  onEdgeSelected: (id: string) => void
}

/**
 * 画布图谱操作的核心 composable。
 *
 * 集中处理所有会“改变节点 / 边内容”的交互：创建节点、清空、自动布局、手动连边，以及拖拽结束后的
 * 快照同步。所有 emit 都委托给 options 注入的宿主回调，让该 composable 与 Vue Flow 外部的业务事件解耦。
 */
export function useCanvasGraph(options: Options) {
  const addNodeCount = ref(0)
  const addEdgeCount = ref(0)

  function getGraphSnapshot(): CreativeGraphSnapshot {
    return {
      nodes: options.nodes.value.map((node) => ({
        id: node.id,
        type: node.type,
        position: { x: node.position.x, y: node.position.y },
        data: {
          title: node.data.title,
          content: node.data.content,
          nodeType: node.data.nodeType,
          tags: [...node.data.tags],
          status: node.data.status,
          icon: node.data.icon,
          typeLabel: node.data.typeLabel,
        },
      })),
      edges: options.edges.value.map((edge) => normalizeEdge(edge)),
    }
  }

  function emitGraphChanged() {
    options.onGraphChanged(getGraphSnapshot())
  }

  /**
   * 计算新建节点的画布坐标。
   *
   * 根据当前视口反推出画布坐标，让节点落在用户正在查看区域的中心附近；连续创建时按计数偏移，
   * 避免堆叠在同一坐标。
   */
  function getNextNodePosition() {
    const viewport = options.getViewport()
    const rect = options.flowShell.value?.getBoundingClientRect()
    const centerX = rect ? rect.width / 2 : 520
    const centerY = rect ? rect.height / 2 : 300
    const offset = addNodeCount.value * 28

    return {
      x: (centerX - viewport.x) / viewport.zoom + offset,
      y: (centerY - viewport.y) / viewport.zoom + offset,
    }
  }

  function handleCreateNode(type: CreativeNodeType, position?: { x: number; y: number }) {
    addNodeCount.value += 1
    const preferredPosition = position ?? getNextNodePosition()
    const node = createCreativeNode(
      type,
      addNodeCount.value,
      findFreeNodePosition(options.nodes.value, preferredPosition),
    )
    options.nodes.value = [...options.nodes.value, node]
    options.onNodeAdded(node)
    emitGraphChanged()
    options.onNodeSelected(node.id)
  }

  function handleAutoArrange() {
    if (options.nodes.value.length <= 1) return

    options.nodes.value = arrangeNodesAsHierarchy(options.nodes.value, options.edges.value)
    emitGraphChanged()
  }

  /**
   * 原地更新节点展示数据（second_revision 变更 A：行内编辑）。
   *
   * 节点组件中的 InlineEditableText 保存时调用；更新 nodes.value 中匹配节点的 data 字段并触发自动保存，
   * 走与拖拽 / 连线相同的“修改 nodes.value 后 emit”路径。
   */
  function updateNodeData(nodeId: string, patch: { title?: string; content?: string }) {
    let changed = false
    options.nodes.value = options.nodes.value.map((node) => {
      if (node.id !== nodeId) return node
      const nextData = { ...node.data }
      if (patch.title !== undefined && patch.title !== nextData.title) {
        nextData.title = patch.title
        changed = true
      }
      if (patch.content !== undefined && patch.content !== nextData.content) {
        nextData.content = patch.content
        changed = true
      }
      return { ...node, data: nextData }
    })
    if (changed) emitGraphChanged()
  }

  /** 删除单个节点及其相关边（右键菜单删除，second_revision 变更 A）。 */
  function removeNode(nodeId: string) {
    options.edges.value = options.edges.value.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    )
    options.nodes.value = options.nodes.value.filter((node) => node.id !== nodeId)
    emitGraphChanged()
  }

  function removeEdge(edgeId: string) {
    options.edges.value = options.edges.value.filter((edge) => edge.id !== edgeId)
    emitGraphChanged()
    options.onEdgeSelected('')
  }

  function handleClearCanvas() {
    const confirmed = window.confirm('确定清空整个画布吗？所有节点和边都会被移除。')
    if (!confirmed) return

    options.nodes.value = []
    options.edges.value = []
    options.onNodeSelected('')
    emitGraphChanged()
  }

  function hasDuplicateEdge(connection: Connection) {
    return options.edges.value.some(
      (edge) =>
        edge.source === connection.source &&
        edge.target === connection.target &&
        (edge.sourceHandle ?? null) === (connection.sourceHandle ?? null) &&
        (edge.targetHandle ?? null) === (connection.targetHandle ?? null),
    )
  }

  function handleConnect(connection: Connection) {
    if (!connection.source || !connection.target || connection.source === connection.target) {
      return
    }
    if (hasDuplicateEdge(connection)) return

    addEdgeCount.value += 1
    const relationType = options.selectedRelationType.value
    const label = getRelationLabel(relationType)

    const edge: CreativeFlowEdge = {
      id: `edge-${connection.source}-${connection.target}-${Date.now()}-${addEdgeCount.value}`,
      source: connection.source,
      target: connection.target,
      label,
      sourceHandle: connection.sourceHandle ?? DEFAULT_SOURCE_HANDLE,
      targetHandle: connection.targetHandle ?? DEFAULT_TARGET_HANDLE,
      type: 'bezier',
      data: {
        label,
        relationType,
      },
    }

    options.edges.value = addEdge(
      normalizeEdge(edge) as Edge,
      options.edges.value as Edge[],
    ) as CreativeFlowEdge[]
    emitGraphChanged()
    options.onEdgeSelected(edge.id)
  }

  function handleEdgeUpdate(payload: { edge: Edge; connection: Connection }) {
    const { edge, connection } = payload
    if (!connection.source || !connection.target || connection.source === connection.target) {
      return
    }
    options.edges.value = updateEdge(
      edge,
      connection,
      options.edges.value as Edge[],
    ) as CreativeFlowEdge[]
    emitGraphChanged()
  }

  function handleNodeDragStop() {
    emitGraphChanged()
  }

  function updateEdgeRelation(edgeId: string, relationType: CreativeRelationType) {
    const label = getRelationLabel(relationType)
    options.edges.value = options.edges.value.map((edge) => {
      if (edge.id !== edgeId) return edge
      return normalizeEdge({
        ...edge,
        label,
        data: {
          ...(edge.data ?? {}),
          label,
          relationType,
        },
      })
    })
    emitGraphChanged()
    options.onEdgeSelected(edgeId)
  }

  function updateEdgeLabel(edgeId: string, label: string) {
    options.edges.value = options.edges.value.map((edge) => {
      if (edge.id !== edgeId) return edge
      return normalizeEdge({
        ...edge,
        label,
        data: { ...(edge.data ?? {}), label },
      })
    })
    emitGraphChanged()
  }

  return {
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
  }
}
