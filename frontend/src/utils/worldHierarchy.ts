import { Position } from '@vue-flow/core'
import type { CreativeFlowEdge, CreativeFlowNode, CreativeGraphSnapshot } from '../types/node'
import { normalizeEdge } from './canvasRelations'

export interface WorldTreeNode {
  id: string
  node: CreativeFlowNode
  children: WorldTreeNode[]
}

/** 全局样式中的卡片宽度为 236px；兄弟节点之间留出一点呼吸空间。 */
const NODE_X_GAP = 260
/** 左上间距需要避开完整卡片高度（约 172px）并保留可见间隔。 */
const WORLD_NODE_HEIGHT = 172
const WORLD_NODE_Y_MARGIN = 56
const NODE_Y_GAP = WORLD_NODE_HEIGHT + WORLD_NODE_Y_MARGIN
const FOREST_GAP = 360
const FOREST_GAP_UNITS = Math.max(1, Math.round(FOREST_GAP / NODE_X_GAP))
const LAYOUT_ORIGIN_X = 80
const LAYOUT_ORIGIN_Y = 60

/** 执行 unitToX 对应的工具转换或计算。 */
function unitToX(unit: number): number {
  return LAYOUT_ORIGIN_X + unit * NODE_X_GAP
}

/** 执行 siblingSort 对应的工具转换或计算。 */
function siblingSort(a: CreativeFlowNode, b: CreativeFlowNode): number {
  return (a.data.sortOrder ?? 0) - (b.data.sortOrder ?? 0)
}

/** 根据 parentId 从扁平世界观节点构建森林；无效父级会变成根节点。 */
export function buildWorldForest(nodes: CreativeFlowNode[]): WorldTreeNode[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const childrenByParent = new Map<string | null, CreativeFlowNode[]>()

  for (const node of nodes) {
    const parentId = node.data.parentId ?? null
    const parentExists = parentId ? nodeById.has(parentId) : true
    const bucketKey = parentExists ? parentId : null
    const bucket = childrenByParent.get(bucketKey) ?? []
    bucket.push(node)
    childrenByParent.set(bucketKey, bucket)
  }

  /** 执行 toTree 对应的工具转换或计算。 */
  function toTree(node: CreativeFlowNode): WorldTreeNode {
    const childNodes = (childrenByParent.get(node.id) ?? []).slice().sort(siblingSort)
    return {
      id: node.id,
      node,
      children: childNodes.map(toTree),
    }
  }

  const roots = (childrenByParent.get(null) ?? []).slice().sort(siblingSort)
  return roots.map(toTree)
}

/** 分配自上而下的树状位置；每个根节点沿 x 轴开启一棵独立树。 */
export function layoutWorldForest(forest: WorldTreeNode[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  let forestCursor = 0

  for (const root of forest) {
    placeTree(root, forestCursor, 0, positions)
    forestCursor += measureTreeWidth(root) + FOREST_GAP_UNITS
  }

  return positions
}

/** 执行 measureTreeWidth 对应的工具转换或计算。 */
function measureTreeWidth(tree: WorldTreeNode): number {
  if (tree.children.length === 0) return 1
  return tree.children.reduce((sum, child) => sum + measureTreeWidth(child), 0)
}

/** 执行 placeTree 对应的工具转换或计算。 */
function placeTree(
  tree: WorldTreeNode,
  leftUnit: number,
  depth: number,
  positions: Map<string, { x: number; y: number }>,
): number {
  if (tree.children.length === 0) {
    positions.set(tree.id, {
      x: unitToX(leftUnit),
      y: LAYOUT_ORIGIN_Y + depth * NODE_Y_GAP,
    })
    return leftUnit + 1
  }

  let cursor = leftUnit
  for (const child of tree.children) {
    cursor = placeTree(child, cursor, depth + 1, positions)
  }

  const firstChild = positions.get(tree.children[0].id)
  const lastChild = positions.get(tree.children[tree.children.length - 1].id)
  const centerX =
    firstChild && lastChild ? (firstChild.x + lastChild.x) / 2 : unitToX(leftUnit)

  positions.set(tree.id, {
    x: centerX,
    y: LAYOUT_ORIGIN_Y + depth * NODE_Y_GAP,
  })

  return cursor
}

/** 为持久化和树状画布推导纯层级边（子节点 → 父节点，归属）。 */
export function hierarchyToEdges(nodes: CreativeFlowNode[]): CreativeFlowEdge[] {
  const edges: CreativeFlowEdge[] = []

  for (const node of nodes) {
    const parentId = node.data.parentId
    if (!parentId) continue

    edges.push(
      normalizeEdge({
        id: `world-hier-${node.id}-${parentId}`,
        source: node.id,
        target: parentId,
        label: '归属',
        sourceHandle: 'top',
        targetHandle: 'bottom',
        type: 'bezier',
        data: {
          label: '归属',
          relationType: 'belongs_to',
        },
      }),
    )
  }

  return edges
}

/** 树状画布边：父节点在上、子节点在下，使用无标签的自上而下贝塞尔线。 */
export function hierarchyToTreeCanvasEdges(nodes: CreativeFlowNode[]): CreativeFlowEdge[] {
  const nodeIds = new Set(nodes.map((node) => node.id))

  return nodes.flatMap((node) => {
    const parentId = node.data.parentId
    if (!parentId || !nodeIds.has(parentId)) return []

    const edge = normalizeEdge({
      id: `world-tree-${node.id}-${parentId}`,
      source: node.id,
      target: parentId,
      sourceHandle: 'top',
      targetHandle: 'bottom',
      type: 'bezier',
      data: {
        relationType: 'belongs_to',
        label: '',
      },
    })

    return [{ ...edge, label: '', data: { ...edge.data, label: '' } }]
  })
}

/** 执行 applyTreeLayout 对应的工具转换或计算。 */
export function applyTreeLayout(nodes: CreativeFlowNode[]): CreativeFlowNode[] {
  const forest = buildWorldForest(nodes)
  const positions = layoutWorldForest(forest)

  // 处于循环或父级链断裂中的节点也需要一个位置。
  let orphanUnit = 0
  if (positions.size > 0) {
    const maxX = Math.max(...[...positions.values()].map((position) => position.x))
    orphanUnit = Math.ceil((maxX - LAYOUT_ORIGIN_X) / NODE_X_GAP) + FOREST_GAP_UNITS
  }
  for (const node of nodes) {
    if (positions.has(node.id)) continue
    positions.set(node.id, { x: unitToX(orphanUnit), y: LAYOUT_ORIGIN_Y })
    orphanUnit += 1
  }

  return nodes.map((node) => {
    const position = positions.get(node.id) ?? node.position
    return {
      ...node,
      position: { x: position.x, y: position.y },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    }
  })
}

/** 执行 buildWorldSaveSnapshot 对应的工具转换或计算。 */
export function buildWorldSaveSnapshot(nodes: CreativeFlowNode[]): CreativeGraphSnapshot {
  return {
    nodes,
    edges: hierarchyToEdges(nodes),
  }
}

/** 执行 nextWorldSortOrder 对应的工具转换或计算。 */
export function nextWorldSortOrder(nodes: CreativeFlowNode[], parentId: string | null): number {
  const siblings = nodes.filter((node) => (node.data.parentId ?? null) === parentId)
  if (siblings.length === 0) return 0
  return Math.max(...siblings.map((node) => node.data.sortOrder ?? 0)) + 1
}

/** 执行 wouldCreateWorldCycle 对应的工具转换或计算。 */
export function wouldCreateWorldCycle(
  nodes: CreativeFlowNode[],
  nodeId: string,
  nextParentId: string | null,
): boolean {
  if (!nextParentId || nextParentId === nodeId) return nextParentId === nodeId

  const parentById = new Map(
    nodes.map((node) => [node.id, node.data.parentId ?? null] as const),
  )

  let cursor: string | null = nextParentId
  while (cursor) {
    if (cursor === nodeId) return true
    cursor = parentById.get(cursor) ?? null
  }

  return false
}

export type WorldMoveTarget =
  | { type: 'root' }
  | { type: 'child'; parentId: string }
  | { type: 'before'; siblingId: string }

/** 执行 renumberSiblingSortOrders 对应的工具转换或计算。 */
function renumberSiblingSortOrders(
  nodes: CreativeFlowNode[],
  parentId: string | null,
  orderedIds: string[],
): CreativeFlowNode[] {
  const orderMap = new Map(orderedIds.map((id, index) => [id, index]))
  return nodes.map((node) => {
    if ((node.data.parentId ?? null) !== parentId) return node
    const order = orderMap.get(node.id)
    if (order === undefined) return node
    return {
      ...node,
      data: {
        ...node.data,
        sortOrder: order,
      },
    }
  })
}

/** 调整世界观笔记的父级或排序；如果移动会产生循环则返回 null。 */
export function moveWorldNode(
  nodes: CreativeFlowNode[],
  draggedId: string,
  target: WorldMoveTarget,
): CreativeFlowNode[] | null {
  const dragged = nodes.find((node) => node.id === draggedId)
  if (!dragged) return null

  let newParentId: string | null
  let insertBeforeId: string | null = null

  if (target.type === 'root') {
    newParentId = null
  } else if (target.type === 'child') {
    newParentId = target.parentId
  } else {
    const sibling = nodes.find((node) => node.id === target.siblingId)
    if (!sibling) return null
    newParentId = sibling.data.parentId ?? null
    insertBeforeId = target.siblingId
  }

  if (newParentId === draggedId) return null
  if (wouldCreateWorldCycle(nodes, draggedId, newParentId)) return null

  const siblings = nodes
    .filter((node) => node.id !== draggedId && (node.data.parentId ?? null) === newParentId)
    .sort(siblingSort)

  let orderedIds: string[]
  if (insertBeforeId) {
    const insertIndex = siblings.findIndex((node) => node.id === insertBeforeId)
    if (insertIndex < 0) {
      orderedIds = [...siblings.map((node) => node.id), draggedId]
    } else {
      orderedIds = [
        ...siblings.slice(0, insertIndex).map((node) => node.id),
        draggedId,
        ...siblings.slice(insertIndex).map((node) => node.id),
      ]
    }
  } else {
    orderedIds = [...siblings.map((node) => node.id), draggedId]
  }

  let updated = nodes.map((node) => {
    if (node.id !== draggedId) return node
    return {
      ...node,
      data: {
        ...node.data,
        parentId: newParentId,
      },
    }
  })

  updated = renumberSiblingSortOrders(updated, newParentId, orderedIds)
  return updated
}

/** 一次性兼容辅助：parentId 缺失时，把旧版 belongs_to 边视作文件夹层级。 */
export function inferWorldHierarchyFromEdges(snapshot: CreativeGraphSnapshot): CreativeGraphSnapshot {
  const hasHierarchy = snapshot.nodes.some((node) => node.data.parentId)
  if (hasHierarchy) return snapshot

  const nodeIds = new Set(snapshot.nodes.map((node) => node.id))
  const parentByChild = new Map<string, string>()

  for (const edge of snapshot.edges) {
    if (edge.data?.relationType !== 'belongs_to') continue
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue
    // child belongs_to parent => source 是子节点，target 是父节点。
    parentByChild.set(edge.source, edge.target)
  }

  if (parentByChild.size === 0) return snapshot

  const nodes = snapshot.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      parentId: parentByChild.get(node.id) ?? null,
    },
  }))

  return { nodes, edges: hierarchyToEdges(nodes) }
}
