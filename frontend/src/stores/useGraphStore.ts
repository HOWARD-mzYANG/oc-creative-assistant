import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { GraphEdgeDto, GraphNodeDto } from '../api/graphApi'
import { loadSubgraph } from '../api/graphApi'

/**
 * Currently open sub-graph store (first_revision decision 6 / phase 3).
 *
 * Mainly serves the two 角色-card routes (CharacterCardList ↔ CharacterCardDetail), letting them share the same
 * sub-graph data and avoiding a second full fetch on the detail page. The Plot/World canvases use useGraphPersistence's
 * injected loading and do not depend on this store.
 */
export const useGraphStore = defineStore('graph', () => {
  const graphId = ref('')
  const nodes = ref<GraphNodeDto[]>([])
  const edges = ref<GraphEdgeDto[]>([])
  const isLoading = ref(false)
  const error = ref('')

  /** Load a sub-graph by graph_id; can force-refresh when it is already the current graph. */
  async function load(targetGraphId: string, force = false): Promise<void> {
    if (!force && graphId.value === targetGraphId && nodes.value.length > 0) return
    isLoading.value = true
    error.value = ''
    try {
      const graph = await loadSubgraph(targetGraphId)
      graphId.value = targetGraphId
      nodes.value = graph.nodes
      edges.value = graph.edges
    } catch (e) {
      error.value = e instanceof Error ? e.message : '子图加载失败'
      nodes.value = []
      edges.value = []
    } finally {
      isLoading.value = false
    }
  }

  /** Get a single node (used by the detail page). */
  function getNode(nodeId: string): GraphNodeDto | undefined {
    return nodes.value.find((node) => node.id === nodeId)
  }

  /** Get a node's outgoing edges (角色 relations, shown as labels rather than drawn lines). */
  function outgoingEdges(nodeId: string): GraphEdgeDto[] {
    return edges.value.filter((edge) => edge.source === nodeId)
  }

  return { graphId, nodes, edges, isLoading, error, load, getNode, outgoingEdges }
})
