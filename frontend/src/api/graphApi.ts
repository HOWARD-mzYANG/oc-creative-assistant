import type { CreativeNodeStatus, CreativeNodeType, CreativeRelationType } from '../types/node'

/** Backend project DTO, used to determine the lifecycle boundary of the current graph. */
export interface GraphProjectDto {
  id: string
  name: string
}

/** Node coordinates saved by the backend; does not include the Vue Flow viewport or computedPosition. */
export interface GraphPositionDto {
  x: number
  y: number
}

/** Backend node DTO; content maps to the full text content of the frontend node. */
export interface GraphNodeDto {
  id: string
  type: CreativeNodeType
  nodeType?: CreativeNodeType | null
  title: string
  content: string
  position: GraphPositionDto
  meta: string
  typeLabel: string
  tags?: string[]
  status?: CreativeNodeStatus
  parentId?: string | null
  sortOrder?: number
}

/** Backend edge waypoint DTO; isomorphic to the frontend CreativeEdgeWaypoint. */
export interface GraphEdgeWaypointDto {
  orientation: 'horizontal' | 'vertical'
  middle: number
  nearSource?: number | null
  nearTarget?: number | null
}

/** Backend edge DTO; the handle fields are used to restore which connection point the edge was drawn from. */
export interface GraphEdgeDto {
  id: string
  source: string
  target: string
  label: string
  relationType?: CreativeRelationType
  sourceHandle?: string | null
  targetHandle?: string | null
  type: string
  animated: boolean
  waypoint?: GraphEdgeWaypointDto | null
}

/** Backend vector index status; a successful SQLite save does not guarantee embedding succeeded, so it needs to be shown separately. */
export interface IndexingStatusDto {
  status: 'not_checked' | 'synced' | 'partial' | 'failed'
  message: string
  provider: string
  model: string
  dimension: number
  expected_nodes: number
  indexed_nodes: number
  missing_node_ids: string[]
  error?: string | null
}

/** The full graph snapshot returned by the read endpoint. */
export interface GraphDto {
  project: GraphProjectDto
  nodes: GraphNodeDto[]
  edges: GraphEdgeDto[]
  indexing?: IndexingStatusDto
}

/** 保存端点请求体；projectId 由 URL 参数提供。 */
export interface SaveGraphDto {
  nodes: GraphNodeDto[]
  edges: GraphEdgeDto[]
}

/** RAG context preview request body; currently only the inspiration debug entry is supported. */
export interface RagContextRequestDto {
  node_id: string
  query: string
  agent_type: 'inspiration'
  top_k: number
}

/** The current node snapshot in the RAG response. */
export interface RagCurrentNodeDto {
  id: string
  type: string
  title: string
  content: string
  tags: string[]
}

/** One-hop graph relation context derived from the canvas edges. */
export interface RagGraphContextItemDto {
  id: string
  type: string
  title: string
  content: string
  relation_label: string
  relation_type: string
  direction: string
}

/** Similar-node context hit by vector retrieval. */
export interface RagVectorContextItemDto {
  id: string
  type: string
  title: string
  content: string
  score: number
}

/** Context entries after the backend has merged and deduplicated them. */
export interface RagMergedContextItemDto {
  id: string
  source: string
  type: string
  title: string
  content: string
}

/** RAG context preview endpoint response. */
export interface RagContextResponseDto {
  current_node: RagCurrentNodeDto
  graph_context: RagGraphContextItemDto[]
  vector_context: RagVectorContextItemDto[]
  merged_context: RagMergedContextItemDto[]
  prompt: string
  debug: {
    query_used: string
    top_k: number
    vector_store: string
    llm_called: boolean
    vector_error?: string | null
  }
}

/** Project-level Lore Memory search request body; does not depend on the currently selected node. */
export interface MemorySearchRequestDto {
  query: string
  node_type?: CreativeNodeType | null
  top_k: number
}

/** Project-level Lore Memory search hit. */
export interface MemorySearchItemDto {
  id: string
  type: CreativeNodeType
  title: string
  content: string
  tags: string[]
  status: CreativeNodeStatus
  score: number
}

/** Project-level Lore Memory search response. */
export interface MemorySearchResponseDto {
  items: MemorySearchItemDto[]
  debug: {
    query_used: string
    top_k: number
    vector_store: string
    llm_called: boolean
    vector_error?: string | null
  }
}

import { requestJson } from './http'

/**
 * Load the graph of the default project.
 *
 * On first launch it first hits the default-project endpoint, triggering the backend to initialize sample data.
 *
 * Returns:
 *   The full graph DTO of the default project.
 */
export async function loadDefaultGraph(): Promise<GraphDto> {
  const project = await requestJson<GraphProjectDto>('/api/projects/default')

  return requestJson<GraphDto>(`/api/projects/${project.id}/graph`)
}

/**
 * 保存项目图快照。
 *
 * The backend uses a whole-graph replace strategy and syncs the vector index after the SQLite commit.
 *
 * Args:
 *   projectId: The current project ID.
 *   graph: The node and edge snapshot to save.
 *
 * Returns:
 *   The graph DTO after the backend has finally persisted it.
 */
export async function saveProjectGraph(projectId: string, graph: SaveGraphDto): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/projects/${projectId}/graph`, {
    method: 'PUT',
    body: JSON.stringify(graph),
  })
}

/**
 * Load a single sub-graph by graph_id (first_revision decision 1).
 *
 * Coexists with the project dimension of loadDefaultGraph / saveProjectGraph: the new three-view
 * workspace (PlotCanvas / CharacterCardList / WorldCanvas) each load by their own graph_id.
 *
 * Args:
 *   graphId: sub-graph ID (from ProjectDetail's plot/character/world_graph_id).
 *
 * Returns:
 *   The node + internal-edge snapshot of that sub-graph.
 */
export async function loadSubgraph(graphId: string): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/graphs/${graphId}`)
}

/**
 * 按 graph_id 保存单个子图快照（整体替换该子图的节点和内部边）。
 *
 * Args:
 *   graphId: sub-graph ID.
 *   graph: The node and edge snapshot to save.
 *
 * Returns:
 *   The sub-graph DTO after the backend has persisted it.
 */
export async function saveSubgraph(graphId: string, graph: SaveGraphDto): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/graphs/${graphId}`, {
    method: 'PUT',
    body: JSON.stringify(graph),
  })
}

/**
 * Load a RAG context preview.
 *
 * This endpoint is currently only for debugging graph relations, vector results, and the prompt; it does not call a real LLM.
 *
 * Args:
 *   payload: The RAG context preview request body.
 *
 * Returns:
 *   The context and prompt built by the backend.
 */
export async function loadRagContext(payload: RagContextRequestDto): Promise<RagContextResponseDto> {
  return requestJson<RagContextResponseDto>('/api/rag/context', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * Search Lore Memory within the current project.
 *
 * This endpoint only returns memory cards hit by vector retrieval; it does not build a prompt and does not call an LLM.
 *
 * Args:
 *   projectId: The current project ID.
 *   payload: Search text, type filter, and number of results.
 *
 * Returns:
 *   Semantically relevant memory entries within the project.
 */
export async function searchProjectMemory(
  projectId: string,
  payload: MemorySearchRequestDto,
): Promise<MemorySearchResponseDto> {
  return requestJson<MemorySearchResponseDto>(`/api/projects/${projectId}/memory/search`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
