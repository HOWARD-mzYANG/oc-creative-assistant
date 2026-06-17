import type { CreativeNodeStatus, CreativeNodeType, CreativeRelationType } from '../types/node'

/** 后端项目 DTO，用于确定当前图谱的生命周期边界。 */
export interface GraphProjectDto {
  id: string
  name: string
}

/** 后端保存的节点坐标；不包含 Vue Flow viewport 或 computedPosition。 */
export interface GraphPositionDto {
  x: number
  y: number
}

/** 后端节点 DTO；content 对应前端节点的完整文本内容。 */
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

/** 后端边路径点 DTO；与前端 CreativeEdgeWaypoint 同构。 */
export interface GraphEdgeWaypointDto {
  orientation: 'horizontal' | 'vertical'
  middle: number
  nearSource?: number | null
  nearTarget?: number | null
}

/** 后端边 DTO；handle 字段用于恢复边是从哪个连接点画出的。 */
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

/** 后端向量索引状态；SQLite 保存成功不代表 embedding 成功，因此需要单独展示。 */
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

/** 读取端点返回的完整图谱快照。 */
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

/** RAG 上下文预览请求体；当前只支持 inspiration 调试入口。 */
export interface RagContextRequestDto {
  node_id: string
  query: string
  agent_type: 'inspiration'
  top_k: number
}

/** RAG 响应中的当前节点快照。 */
export interface RagCurrentNodeDto {
  id: string
  type: string
  title: string
  content: string
  tags: string[]
}

/** 从画布边推导出的一跳图关系上下文。 */
export interface RagGraphContextItemDto {
  id: string
  type: string
  title: string
  content: string
  relation_label: string
  relation_type: string
  direction: string
}

/** 向量检索命中的相似节点上下文。 */
export interface RagVectorContextItemDto {
  id: string
  type: string
  title: string
  content: string
  score: number
}

/** 后端合并去重后的上下文条目。 */
export interface RagMergedContextItemDto {
  id: string
  source: string
  type: string
  title: string
  content: string
}

/** RAG 上下文预览端点响应。 */
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

/** 项目级设定记忆搜索请求体；不依赖当前选中的节点。 */
export interface MemorySearchRequestDto {
  query: string
  node_type?: CreativeNodeType | null
  top_k: number
}

/** 项目级设定记忆搜索命中项。 */
export interface MemorySearchItemDto {
  id: string
  type: CreativeNodeType
  title: string
  content: string
  tags: string[]
  status: CreativeNodeStatus
  score: number
}

/** 项目级设定记忆搜索响应。 */
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
 * 加载默认项目的图谱。
 *
 * 首次启动时会先请求默认项目端点，触发后端初始化示例数据。
 *
 * 返回：
 *   默认项目的完整图谱 DTO。
 */
export async function loadDefaultGraph(): Promise<GraphDto> {
  const project = await requestJson<GraphProjectDto>('/api/projects/default')

  return requestJson<GraphDto>(`/api/projects/${project.id}/graph`)
}

/**
 * 保存项目图快照。
 *
 * 后端使用整体替换图谱的策略，并在 SQLite 提交后同步向量索引。
 *
 * 参数：
 *   projectId: 当前项目 ID。
 *   graph: 要保存的节点和边快照。
 *
 * 返回：
 *   后端最终持久化后的图谱 DTO。
 */
export async function saveProjectGraph(projectId: string, graph: SaveGraphDto): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/projects/${projectId}/graph`, {
    method: 'PUT',
    body: JSON.stringify(graph),
  })
}

/**
 * 按 graph_id 加载单个子图（first_revision 决策 1）。
 *
 * 与 loadDefaultGraph / saveProjectGraph 的项目维度并存：新的三视图工作区
 *（PlotCanvas / CharacterCardList / WorldCanvas）各自按自己的 graph_id 加载。
 *
 * 参数：
 *   graphId: 子图 ID（来自 ProjectDetail 的 plot/character/world_graph_id）。
 *
 * 返回：
 *   该子图的节点 + 内部边快照。
 */
export async function loadSubgraph(graphId: string): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/graphs/${graphId}`)
}

/**
 * 按 graph_id 保存单个子图快照（整体替换该子图的节点和内部边）。
 *
 * 参数：
 *   graphId: 子图 ID。
 *   graph: 要保存的节点和边快照。
 *
 * 返回：
 *   后端持久化后的子图 DTO。
 */
export async function saveSubgraph(graphId: string, graph: SaveGraphDto): Promise<GraphDto> {
  return requestJson<GraphDto>(`/api/graphs/${graphId}`, {
    method: 'PUT',
    body: JSON.stringify(graph),
  })
}

/**
 * 加载 RAG 上下文预览。
 *
 * 该端点目前仅用于调试图关系、向量结果和 prompt，不会调用真实 LLM。
 *
 * 参数：
 *   payload: RAG 上下文预览请求体。
 *
 * 返回：
 *   后端构建的上下文和 prompt。
 */
export async function loadRagContext(payload: RagContextRequestDto): Promise<RagContextResponseDto> {
  return requestJson<RagContextResponseDto>('/api/rag/context', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * 在当前项目中搜索设定记忆。
 *
 * 该端点只返回向量检索命中的记忆卡片，不构建 prompt，也不调用 LLM。
 *
 * 参数：
 *   projectId: 当前项目 ID。
 *   payload: 搜索文本、类型过滤和结果数量。
 *
 * 返回：
 *   项目内语义相关的记忆条目。
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
