import { MarkerType } from '@vue-flow/core'
import {
  RELATION_TYPE_OPTIONS,
  type CreativeFlowEdge,
  type CreativeFlowNode,
  type CreativeRelationType,
} from '../types/node'

export const DEFAULT_RELATION_TYPE: CreativeRelationType = 'relates_to'
export const DEFAULT_SOURCE_HANDLE = 'right'
export const DEFAULT_TARGET_HANDLE = 'left'

interface RelationEdgeStyle {
  color: string
  labelBg: string
  animated?: boolean
}

/**
 * 关系类型 -> 视觉样式查找表。
 *
 * 颜色、浅色背景、是否启用流动动画会映射到描边、标签背景和 animated 属性。这里使用 record
 * 而不是 switch，后续新增关系类型时只需要修改这一处。
 */
// 调色盘控制在紫 / 橙 / 玫红（冲突感）/ 灰色范围内，以呼应整体轻梦幻的基调。
const relationEdgeStyles: Record<CreativeRelationType, RelationEdgeStyle> = {
  relates_to: { color: '#a29bc4', labelBg: '#f6f4fb' },
  causes: { color: '#f59e0b', labelBg: '#fff7ed' },
  belongs_to: { color: '#8b5cf6', labelBg: '#f5f3ff' },
  conflicts_with: { color: '#fb7185', labelBg: '#fff1f3', animated: true },
  references: { color: '#6366f1', labelBg: '#eef2ff' },
  develops_into: { color: '#a855f7', labelBg: '#faf5ff' },
}

export function getRelationLabel(relationType: CreativeRelationType): string {
  return RELATION_TYPE_OPTIONS.find((option) => option.value === relationType)?.label ?? '相关'
}

export function getRelationStyle(relationType: CreativeRelationType): RelationEdgeStyle {
  return relationEdgeStyles[relationType] ?? relationEdgeStyles.relates_to
}

/**
 * 克隆节点并写入前端展示状态。
 *
 * Vue Flow 会在交互过程中修改节点对象；这里避免直接改动父组件传入的 props。highlighted 集合控制
 * “刚出现节点”的短暂闪烁，选中状态由 selectedNodeId 决定。
 *
 * 参数：
 *   node: 源节点。
 *   selectedNodeId: 当前选中节点 ID。
 *   highlighted: 当前需要闪烁的节点 ID 集合。
 *
 * 返回：
 *   带展示状态字段的节点副本。
 */
export function cloneNode(
  node: CreativeFlowNode,
  selectedNodeId: string,
  highlighted: Set<string>,
): CreativeFlowNode {
  return {
    ...node,
    class: highlighted.has(node.id) ? 'is-highlighted' : '',
    data: { ...node.data, isActive: node.id === selectedNodeId },
  }
}

/**
 * 补齐边的展示字段和业务关系类型。
 *
 * 用于处理后端、父组件或 Vue Flow 返回的边，统一补齐 markerEnd、stroke、label background 等视觉字段，
 * 并确保 sourceHandle / targetHandle / type 等必需字段不丢失。
 *
 * 参数：
 *   edge: 原始边。
 *   highlighted: 当前需要闪烁的边 ID 集合；默认空集合（用于保存快照场景）。
 *
 * 返回：
 *   可稳定渲染并保存的边对象。
 */
export function normalizeEdge(
  edge: CreativeFlowEdge,
  highlighted: Set<string> = new Set(),
  selected = false,
): CreativeFlowEdge {
  const relationType = edge.data?.relationType ?? DEFAULT_RELATION_TYPE
  const label = edge.data?.label || edge.label || getRelationLabel(relationType)
  const relationStyle = getRelationStyle(relationType)
  const classNames = [
    'creative-edge',
    `creative-edge--${relationType}`,
    highlighted.has(edge.id) ? 'is-highlighted' : '',
    selected ? 'is-selected' : '',
  ].filter(Boolean)

  return {
    ...edge,
    selected,
    label,
    sourceHandle: edge.sourceHandle ?? DEFAULT_SOURCE_HANDLE,
    targetHandle: edge.targetHandle ?? DEFAULT_TARGET_HANDLE,
    type: 'bezier',
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: relationStyle.color,
    },
    animated: Boolean(edge.animated || relationStyle.animated),
    class: classNames.join(' '),
    style: {
      stroke: relationStyle.color,
    },
    labelStyle: {
      fill: relationStyle.color,
      fontWeight: 700,
    },
    labelBgStyle: {
      fill: relationStyle.labelBg,
      stroke: relationStyle.color,
    },
    interactionWidth: 24,
    data: {
      ...(edge.data ?? {}),
      label,
      relationType,
    },
  }
}
