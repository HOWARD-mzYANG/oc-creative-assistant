import type { CSSProperties } from 'vue'
import type { Edge, EdgeMarkerType, Position } from '@vue-flow/core'

/** Node types currently supported by the canvas; must stay consistent with the backend DTO, the node factory and the Vue Flow slot names. */
export type CreativeNodeType = 'character' | 'plot' | 'worldbuilding' | 'idea' | 'research' | 'structure'

/** Node sync status, currently used to express the future UI state after RAG/Agent processing. */
export type CreativeNodeStatus = 'draft' | 'synced' | 'outdated'

/** Edge relation types express creative semantics, not workflow execution order. */
export type CreativeRelationType =
  | 'relates_to'
  | 'causes'
  | 'belongs_to'
  | 'conflicts_with'
  | 'references'
  | 'develops_into'

/** Display options for edge relation types. */
export const RELATION_TYPE_OPTIONS: Array<{ value: CreativeRelationType; label: string }> = [
  { value: 'relates_to', label: 'relates to' },
  { value: 'causes', label: 'causes' },
  { value: 'belongs_to', label: 'belongs to' },
  { value: 'conflicts_with', label: 'conflicts with' },
  { value: 'references', label: 'references' },
  { value: 'develops_into', label: 'develops into' },
]

/**
 * Node business data.
 *
 * This structure is persisted together with the graph; `isActive` is purely a frontend selection state and is not written to the backend.
 */
export interface CreativeNodeData {
  /** Node title, used for the canvas card and the right-hand detail editor. */
  title: string
  /** Full node content; the canvas only shows a summary, while the right-hand panel handles editing the full text. */
  content: string
  /** The node's business type, placed in data so the right-hand editor does not depend on Vue Flow's outer type. */
  nodeType: CreativeNodeType
  /** Tags are used for later filtering and RAG indexing; for now they are stored as a string array. */
  tags: string[]
  /** The sync status is currently just a UI placeholder and does not mean ChromaDB or the Agent is actually wired in. */
  status: CreativeNodeStatus
  /** Display icon, so node components do not repeatedly write type mappings. */
  icon: string
    /** Display type label, so node components do not repeatedly write type mappings. */
  typeLabel: string
  /** 世界观 folder parent; null means a root tree. Other node types ignore this field. */
  parentId?: string | null
  /** Sibling order under the same parent in the world folder tree. */
  sortOrder?: number
  /** Frontend selection state, serving canvas rendering only and not part of persistence. */
  isActive?: boolean
}

/** The minimal form of a business node in Vue Flow, to avoid spreading runtime fields directly into application state. */
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

/** A business edge only stores the fields needed to restore the canvas; markerEnd is a frontend rendering supplement. */
export interface CreativeFlowEdge {
  id: string
  source: string
  target: string
  /** Vue Flow's built-in label field handles direct display on the canvas. */
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
  /** Vue Flow runtime selection state; not persisted to the backend. */
  selected?: boolean
  data: CreativeEdgeData
}

export interface CreativeEdgeWaypoint {
  orientation: 'horizontal' | 'vertical'
  /** Perp coordinate of the middle segment - vertical: x; horizontal: y. */
  middle: number
  /** Perp coordinate of the segment near source - vertical: y; horizontal: x. */
  nearSource?: number
  /** Perp coordinate of the segment near target - vertical: y; horizontal: x. */
  nearTarget?: number
}

/** Edge business data. */
export interface CreativeEdgeData {
  /** The edge label is user-editable creative relation text. */
  label: string
  /** The relation type is used for later filtering, structure organization and RAG retrieval expansion. */
  relationType: CreativeRelationType
  /** The user's custom-dragged middle position; when unset, it is computed automatically from the source/target geometry. */
  waypoint?: CreativeEdgeWaypoint
}

/** Compatibility type used when passing to Vue Flow utility functions. */
export type VueFlowCompatibleEdge = Edge & CreativeFlowEdge

/** The savable graph snapshot passed between AppShell and CanvasWorkspace. */
export interface CreativeGraphSnapshot {
  nodes: CreativeFlowNode[]
  edges: CreativeFlowEdge[]
}
