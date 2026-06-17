import type { CSSProperties } from 'vue'
import type { Edge, EdgeMarkerType, Position } from '@vue-flow/core'

/** 画布当前支持的节点类型；必须与后端 DTO、节点工厂和 Vue Flow 插槽名保持一致。 */
export type CreativeNodeType = 'character' | 'plot' | 'worldbuilding' | 'idea' | 'research' | 'structure'

/** 节点同步状态，目前用于表达 RAG / 智能体处理后的未来 UI 状态。 */
export type CreativeNodeStatus = 'draft' | 'synced' | 'outdated'

/** 边关系类型表达创作语义，不表达工作流执行顺序。 */
export type CreativeRelationType =
  | 'relates_to'
  | 'causes'
  | 'belongs_to'
  | 'conflicts_with'
  | 'references'
  | 'develops_into'

/** 边关系类型的显示选项。 */
export const RELATION_TYPE_OPTIONS: Array<{ value: CreativeRelationType; label: string }> = [
  { value: 'relates_to', label: '相关' },
  { value: 'causes', label: '导致' },
  { value: 'belongs_to', label: '归属' },
  { value: 'conflicts_with', label: '冲突' },
  { value: 'references', label: '引用' },
  { value: 'develops_into', label: '发展为' },
]

/**
 * 节点业务数据。
 *
 * 该结构会随图谱一起持久化；`isActive` 只是前端选中状态，不会写入后端。
 */
export interface CreativeNodeData {
  /** 节点标题，用于画布卡片和右侧详情编辑器。 */
  title: string
  /** 节点完整内容；画布只显示摘要，右侧面板负责编辑全文。 */
  content: string
  /** 节点业务类型；放在 data 中，避免右侧编辑器依赖 Vue Flow 外层 type。 */
  nodeType: CreativeNodeType
  /** 标签用于后续过滤和 RAG 索引；目前以字符串数组保存。 */
  tags: string[]
  /** 同步状态目前只是 UI 占位，不代表 ChromaDB 或智能体已真实接入。 */
  status: CreativeNodeStatus
  /** 显示图标，避免节点组件重复编写类型映射。 */
  icon: string
  /** 显示类型标签，避免节点组件重复编写类型映射。 */
  typeLabel: string
  /** 世界观文件夹父级；null 表示根节点。其他节点类型忽略该字段。 */
  parentId?: string | null
  /** 世界观文件夹树中同父级下的排序。 */
  sortOrder?: number
  /** 前端选中状态，仅服务画布渲染，不参与持久化。 */
  isActive?: boolean
}

/** Vue Flow 中业务节点的最小形态，避免把运行时字段直接扩散到应用状态。 */
export interface CreativeFlowNode {
  id: string
  type: CreativeNodeType
  position: {
    x: number
    y: number
  }
  sourcePosition?: Position
  targetPosition?: Position
  class?: string
  data: CreativeNodeData
}

/** 业务边只保存恢复画布所需字段；markerEnd 是前端渲染补充。 */
export interface CreativeFlowEdge {
  id: string
  source: string
  target: string
  /** Vue Flow 内置 label 字段负责在画布上直接显示。 */
  label?: string
  sourceHandle?: string | null
  targetHandle?: string | null
  type?: string
  animated?: boolean
  markerEnd?: EdgeMarkerType
  class?: string
  style?: CSSProperties
  labelStyle?: CSSProperties
  labelBgStyle?: CSSProperties
  interactionWidth?: number
  /** Vue Flow 运行时选中状态，不持久化到后端。 */
  selected?: boolean
  data: CreativeEdgeData
}

export interface CreativeEdgeWaypoint {
  orientation: 'horizontal' | 'vertical'
  /** 中间线段的垂直方向坐标；vertical 时为 x，horizontal 时为 y。 */
  middle: number
  /** 靠近源点线段的垂直方向坐标；vertical 时为 y，horizontal 时为 x。 */
  nearSource?: number
  /** 靠近目标点线段的垂直方向坐标；vertical 时为 y，horizontal 时为 x。 */
  nearTarget?: number
}

/** 边业务数据。 */
export interface CreativeEdgeData {
  /** 边标签是用户可编辑的创作关系文本。 */
  label: string
  /** 关系类型用于后续过滤、结构整理和 RAG 检索扩展。 */
  relationType: CreativeRelationType
  /** 用户自定义拖拽出的中段位置；未设置时根据源点 / 目标点几何关系自动计算。 */
  waypoint?: CreativeEdgeWaypoint
}

/** 传给 Vue Flow 工具函数时使用的兼容类型。 */
export type VueFlowCompatibleEdge = Edge & CreativeFlowEdge

/** AppShell 与 CanvasWorkspace 之间传递的可保存图谱快照。 */
export interface CreativeGraphSnapshot {
  nodes: CreativeFlowNode[]
  edges: CreativeFlowEdge[]
}
