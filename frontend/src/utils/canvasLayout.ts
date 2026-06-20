import type { CreativeFlowEdge, CreativeFlowNode } from '../types/node'

export interface CanvasPoint {
  x: number
  y: number
}

const NODE_WIDTH = 260
const NODE_HEIGHT = 150
const NODE_GAP_X = 90
const NODE_GAP_Y = 70
const STEP_X = NODE_WIDTH + NODE_GAP_X
const STEP_Y = NODE_HEIGHT + NODE_GAP_Y
const DEFAULT_X = 120
const DEFAULT_Y = 120
const MAX_COLUMNS = 10
const MAX_ROW_RADIUS = 10
const COMPONENT_GAP_ROWS = 1

/** 执行 rowOffsets 对应的工具转换或计算。 */
function rowOffsets(radius: number) {
  const offsets = [0]
  for (let value = 1; value <= radius; value += 1) {
    offsets.push(value)
  }
  for (let value = 1; value <= radius; value += 1) {
    offsets.push(-value)
  }
  return offsets
}

/** 执行 overlaps 对应的工具转换或计算。 */
function overlaps(candidate: CanvasPoint, node: CreativeFlowNode) {
  return (
    candidate.x < node.position.x + NODE_WIDTH + NODE_GAP_X &&
    candidate.x + NODE_WIDTH + NODE_GAP_X > node.position.x &&
    candidate.y < node.position.y + NODE_HEIGHT + NODE_GAP_Y &&
    candidate.y + NODE_HEIGHT + NODE_GAP_Y > node.position.y
  )
}

/** 执行 isFree 对应的工具转换或计算。 */
function isFree(candidate: CanvasPoint, nodes: CreativeFlowNode[]) {
  return nodes.every((node) => !overlaps(candidate, node))
}

/** 执行 findFreeNodePosition 对应的工具转换或计算。 */
export function findFreeNodePosition(
  nodes: CreativeFlowNode[],
  preferred: CanvasPoint = { x: DEFAULT_X, y: DEFAULT_Y },
): CanvasPoint {
  const offsets = rowOffsets(MAX_ROW_RADIUS)

  for (let column = 0; column < MAX_COLUMNS; column += 1) {
    for (const rowOffset of offsets) {
      const candidate = {
        x: preferred.x + column * STEP_X,
        y: preferred.y + rowOffset * STEP_Y,
      }
      if (isFree(candidate, nodes)) {
        return candidate
      }
    }
  }

  const fallbackIndex = nodes.length
  return {
    x: preferred.x + (fallbackIndex % MAX_COLUMNS) * STEP_X,
    y: preferred.y + (MAX_ROW_RADIUS + Math.floor(fallbackIndex / MAX_COLUMNS) + 1) * STEP_Y,
  }
}

/** 执行 arrangeNodesInGrid 对应的工具转换或计算。 */
export function arrangeNodesInGrid(nodes: CreativeFlowNode[]): CreativeFlowNode[] {
  if (nodes.length <= 1) {
    return nodes.map((node) => ({ ...node, position: { ...node.position } }))
  }

  const minX = Math.min(...nodes.map((node) => node.position.x))
  const minY = Math.min(...nodes.map((node) => node.position.y))
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)))

  return nodes.map((node, index) => ({
    ...node,
    position: {
      x: Math.round(
        (Number.isFinite(minX) ? minX : DEFAULT_X) + (index % columns) * STEP_X,
      ),
      y: Math.round(
        (Number.isFinite(minY) ? minY : DEFAULT_Y) + Math.floor(index / columns) * STEP_Y,
      ),
    },
  }))
}

/** 执行 sortByCurrentPosition 对应的工具转换或计算。 */
function sortByCurrentPosition(a: CreativeFlowNode, b: CreativeFlowNode) {
  return a.position.y - b.position.y || a.position.x - b.position.x || a.id.localeCompare(b.id)
}

/** 执行 buildDirectedAdjacency 对应的工具转换或计算。 */
function buildDirectedAdjacency(nodes: CreativeFlowNode[], edges: CreativeFlowEdge[]) {
  const nodeIds = new Set(nodes.map((node) => node.id))
  const outgoing = new Map<string, string[]>()
  const incoming = new Map<string, string[]>()

  for (const node of nodes) {
    outgoing.set(node.id, [])
    incoming.set(node.id, [])
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target) || edge.source === edge.target) {
      continue
    }
    outgoing.get(edge.source)?.push(edge.target)
    incoming.get(edge.target)?.push(edge.source)
  }

  const order = new Map(nodes.map((node, index) => [node.id, index]))
  for (const childIds of outgoing.values()) {
    childIds.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0))
  }
  for (const parentIds of incoming.values()) {
    parentIds.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0))
  }

  return { outgoing, incoming }
}

/** 执行 buildPrimaryForest 对应的工具转换或计算。 */
function buildPrimaryForest(
  nodes: CreativeFlowNode[],
  edges: CreativeFlowEdge[],
): { roots: string[]; childrenByParent: Map<string, string[]> } | null {
  const sortedNodes = [...nodes].sort(sortByCurrentPosition)
  const { outgoing, incoming } = buildDirectedAdjacency(sortedNodes, edges)
  const hasAnyEdge = [...outgoing.values()].some((childIds) => childIds.length > 0)

  if (!hasAnyEdge) {
    return null
  }

  const assigned = new Set<string>()
  const roots: string[] = []
  const childrenByParent = new Map<string, string[]>(sortedNodes.map((node) => [node.id, []]))
  const rootCandidates = sortedNodes.filter((node) => (incoming.get(node.id)?.length ?? 0) === 0)
  const traversalSeeds = rootCandidates.length > 0 ? rootCandidates : sortedNodes

  /** 执行 visit 对应的工具转换或计算。 */
  function visit(nodeId: string, path: Set<string>) {
    const childIds = outgoing.get(nodeId) ?? []
    for (const childId of childIds) {
      if (path.has(childId) || assigned.has(childId)) {
        continue
      }

      assigned.add(childId)
      childrenByParent.get(nodeId)?.push(childId)
      visit(childId, new Set([...path, childId]))
    }
  }

  for (const node of traversalSeeds) {
    if (assigned.has(node.id)) {
      continue
    }
    roots.push(node.id)
    assigned.add(node.id)
    visit(node.id, new Set([node.id]))
  }

  for (const node of sortedNodes) {
    if (assigned.has(node.id)) {
      continue
    }
    roots.push(node.id)
    assigned.add(node.id)
    visit(node.id, new Set([node.id]))
  }

  return { roots, childrenByParent }
}

/** 执行 arrangeNodesAsHierarchy 对应的工具转换或计算。 */
export function arrangeNodesAsHierarchy(
  nodes: CreativeFlowNode[],
  edges: CreativeFlowEdge[],
): CreativeFlowNode[] {
  if (nodes.length <= 1) {
    return nodes.map((node) => ({ ...node, position: { ...node.position } }))
  }

  const primaryForest = buildPrimaryForest(nodes, edges)
  if (!primaryForest) {
    return arrangeNodesInGrid(nodes)
  }
  const forest = primaryForest

  const minX = Math.min(...nodes.map((node) => node.position.x))
  const minY = Math.min(...nodes.map((node) => node.position.y))
  const originX = Number.isFinite(minX) ? minX : DEFAULT_X
  const originY = Number.isFinite(minY) ? minY : DEFAULT_Y
  const spanCache = new Map<string, number>()
  const placed = new Map<string, CanvasPoint>()

  /** 执行 subtreeSpan 对应的工具转换或计算。 */
  function subtreeSpan(nodeId: string): number {
    const cached = spanCache.get(nodeId)
    if (cached !== undefined) {
      return cached
    }

    const childIds = forest.childrenByParent.get(nodeId) ?? []
    const span = Math.max(
      1,
      childIds.reduce((total, childId) => total + subtreeSpan(childId), 0),
    )
    spanCache.set(nodeId, span)
    return span
  }

  /** 执行 place 对应的工具转换或计算。 */
  function place(nodeId: string, depth: number, topRow: number) {
    const childIds = forest.childrenByParent.get(nodeId) ?? []
    if (childIds.length === 0) {
      placed.set(nodeId, {
        x: Math.round(originX + depth * STEP_X),
        y: Math.round(originY + topRow * STEP_Y),
      })
      return
    }

    let childTop = topRow
    for (const childId of childIds) {
      place(childId, depth + 1, childTop)
      childTop += subtreeSpan(childId)
    }

    const firstChild = placed.get(childIds[0])
    const lastChild = placed.get(childIds[childIds.length - 1])
    placed.set(nodeId, {
      x: Math.round(originX + depth * STEP_X),
      y: Math.round(((firstChild?.y ?? originY) + (lastChild?.y ?? originY)) / 2),
    })
  }

  let topRow = 0
  for (const rootId of forest.roots) {
    place(rootId, 0, topRow)
    topRow += subtreeSpan(rootId) + COMPONENT_GAP_ROWS
  }

  return nodes.map((node) => ({
    ...node,
    position: placed.get(node.id) ?? { ...node.position },
  }))
}
