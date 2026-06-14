import type { Ref } from 'vue'
import type { CreativeFlowEdge, CreativeFlowNode, CreativeGraphSnapshot } from '../types/node'

const FORM_AUTO_SAVE_DELAY_MS = 3000
const QUICK_AUTO_SAVE_DELAY_MS = 300

interface Options {
  graphSnapshot: Ref<CreativeGraphSnapshot>
  selectedNodeId: Ref<string>
  selectedEdgeId: Ref<string>
  setGraphSnapshot: (snapshot: CreativeGraphSnapshot, shouldPushToCanvas?: boolean) => void
  scheduleAutoSave: (delayMs?: number) => void
  recordHistory?: () => void
  undo?: () => void
  redo?: () => void
}
/**
 * Centralizes graph mutations triggered by the right detail panel and keyboard shortcuts.
 *
 * All mutations enter the main flow via setGraphSnapshot, triggering the unified debounced auto-save; deleting a node
 * also removes its related edges, matching the backend's ondelete=CASCADE behavior. Keyboard shortcuts
 * keep the default text-editing semantics inside input controls.
 */
export function useGraphMutations(options: Options) {
  const { graphSnapshot, selectedNodeId, selectedEdgeId, setGraphSnapshot, scheduleAutoSave } = options
  const { recordHistory, undo, redo } = options

  function handleNodeUpdated(updatedNode: CreativeFlowNode) {
    const nextSnapshot: CreativeGraphSnapshot = {
      nodes: graphSnapshot.value.nodes.map((node) => (node.id === updatedNode.id ? updatedNode : node)),
      edges: graphSnapshot.value.edges,
    }
    setGraphSnapshot(nextSnapshot, true)
    scheduleAutoSave(FORM_AUTO_SAVE_DELAY_MS)
  }

  function handleEdgeUpdated(updatedEdge: CreativeFlowEdge) {
    const nextSnapshot: CreativeGraphSnapshot = {
      nodes: graphSnapshot.value.nodes,
      edges: graphSnapshot.value.edges.map((edge) => (edge.id === updatedEdge.id ? updatedEdge : edge)),
    }
    setGraphSnapshot(nextSnapshot, true)
    scheduleAutoSave(FORM_AUTO_SAVE_DELAY_MS)
  }

  function handleNodeDeleted(nodeId: string) {
    const node = graphSnapshot.value.nodes.find((item) => item.id === nodeId)
    if (!node) {
      return
    }
    const confirmed = window.confirm(`Are you sure you want to delete the node "${node.data.title}"? Its related edges will be deleted too.`)
    if (!confirmed) {
      return
    }
    recordHistory?.()
    const nextSnapshot: CreativeGraphSnapshot = {
      nodes: graphSnapshot.value.nodes.filter((item) => item.id !== nodeId),
      edges: graphSnapshot.value.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    }
    selectedNodeId.value = ''
    selectedEdgeId.value = ''
    setGraphSnapshot(nextSnapshot, true)
    scheduleAutoSave(QUICK_AUTO_SAVE_DELAY_MS)
  }

  function handleEdgeDeleted(edgeId: string) {
    recordHistory?.()
    const nextSnapshot: CreativeGraphSnapshot = {
      nodes: graphSnapshot.value.nodes,
      edges: graphSnapshot.value.edges.filter((edge) => edge.id !== edgeId),
    }
    selectedEdgeId.value = ''
    setGraphSnapshot(nextSnapshot, true)
    scheduleAutoSave(QUICK_AUTO_SAVE_DELAY_MS)
  }

  function isTypingTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) {
      return false
    }
    return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && (event.key === 'z' || event.key === 'Z')) {
      if (isTypingTarget(event.target)) return
      event.preventDefault()
      if (event.shiftKey) redo?.()
      else undo?.()
      return
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === 'y' || event.key === 'Y')) {
      if (isTypingTarget(event.target)) return
      event.preventDefault()
      redo?.()
      return
    }
    if (event.key !== 'Delete' && event.key !== 'Backspace') {
      return
    }
    if (isTypingTarget(event.target)) {
      return
    }
    if (selectedNodeId.value) {
      event.preventDefault()
      event.stopPropagation()
      handleNodeDeleted(selectedNodeId.value)
      return
    }
    if (selectedEdgeId.value) {
      event.preventDefault()
      event.stopPropagation()
      handleEdgeDeleted(selectedEdgeId.value)
    }
  }

  return {
    handleNodeUpdated,
    handleEdgeUpdated,
    handleNodeDeleted,
    handleEdgeDeleted,
    handleGlobalKeydown,
  }
}
