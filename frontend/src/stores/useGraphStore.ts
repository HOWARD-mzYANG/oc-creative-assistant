import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { GraphEdgeDto, GraphNodeDto } from '../api/graphApi'
import { loadSubgraph } from '../api/graphApi'

/**
 * 当前打开子图的状态仓库（first_revision 决策 6 / 第 3 阶段）。
 *
 * 主要服务两个角色卡路由（CharacterCardList ↔ CharacterCardDetail），让它们共享同一份子图数据，避免详情页
 * 再做一次完整拉取。Plot / World 画布使用 useGraphPersistence 注入的加载逻辑，不依赖该 store。
 */
export const useGraphStore = defineStore('graph', () => {
  const graphId = ref('')
  const nodes = ref<GraphNodeDto[]>([])
  const edges = ref<GraphEdgeDto[]>([])
  const isLoading = ref(false)
  const error = ref('')

  /** 按 graph_id 加载子图；当它已经是当前子图时也可强制刷新。 */
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

  /** 获取单个节点（详情页使用）。 */
  function getNode(nodeId: string): GraphNodeDto | undefined {
    return nodes.value.find((node) => node.id === nodeId)
  }

  /** 获取节点的出边（角色关系以标签展示，而不是绘制连线）。 */
  function outgoingEdges(nodeId: string): GraphEdgeDto[] {
    return edges.value.filter((edge) => edge.source === nodeId)
  }

  return { graphId, nodes, edges, isLoading, error, load, getNode, outgoingEdges }
})
