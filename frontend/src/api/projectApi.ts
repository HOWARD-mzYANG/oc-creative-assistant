import type {
  ProjectCreatePayload,
  ProjectDetail,
  ProjectSeed,
  ProjectSummary,
} from '../types/project'
import { requestJson, backendBaseUrl } from './http'


/**
 * 项目 API 客户端（first_revision 第 1 阶段）。
 *
 * 映射到后端 /api/projects/*。子图节点 / 边的读写仍通过 graphApi 的 loadSubgraph / saveSubgraph
 * 按 graph_id 处理。
 */
export interface OcExport {
  format: string
  version: number
  project: { name: string; description: string }
  nodes: Array<{
    id: string
    node_type: string
    title: string
    content: string
    meta: { tags?: string[]; status?: string; fields?: Record<string, string> }
    position_x: number
    position_y: number
    sort_order: number
  }>
  edges: Array<{
    source: string
    target: string
    label: string
    relation_type: string
    edge_type: string
    sort_order: number
  }>
}

/** 获取解析后的项目快照（用于 PDF 渲染）。 */
export async function getProjectExport(projectId: string): Promise<OcExport> {
  return requestJson<OcExport>(`/api/projects/${projectId}/export.oc`)
}

/** 下载项目的无损 .oc 快照。 */
export async function exportProjectOc(projectId: string): Promise<Blob> {
  const data = await requestJson<unknown>(`/api/projects/${projectId}/export.oc`)
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
}
/** 将 .oc 文件导入为新项目；返回新项目详情。 */
export async function importProjectOc(file: File): Promise<{ id: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${backendBaseUrl}/api/projects/import.oc`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`导入失败：HTTP ${res.status}`)
  return res.json()
}

/** 列出所有项目（项目库卡片）。 */
export async function listProjects(): Promise<ProjectSummary[]> {
  return requestJson<ProjectSummary[]>('/api/projects')
}

/** 创建项目；后端会自动创建三个子图。 */
export async function createProject(payload: ProjectCreatePayload): Promise<ProjectDetail> {
  return requestJson<ProjectDetail>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 读取项目详情（包含三个 graph_id 和最新 seed）。 */
export async function getProjectDetail(projectId: string): Promise<ProjectDetail> {
  return requestJson<ProjectDetail>(`/api/projects/${projectId}`)
}

/** 更新项目名称 / 描述 / 封面图（概览页编辑简介时使用）。 */
export async function updateProject(
  projectId: string,
  payload: { name?: string; description?: string; cover_image?: string },
): Promise<ProjectDetail> {
  return requestJson<ProjectDetail>(`/api/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/** 读取节点的自由表单字段（角色卡）。 */
export async function getNodeFields(
  projectId: string,
  nodeId: string,
): Promise<{ node_id: string; fields: Record<string, string> }> {
  return requestJson(`/api/projects/${projectId}/nodes/${nodeId}/fields`)
}

/** 整体替换节点的自由表单字段（角色卡）。 */
export async function saveNodeFields(
  projectId: string,
  nodeId: string,
  fields: Record<string, string>,
): Promise<{ node_id: string; fields: Record<string, string> }> {
  return requestJson(`/api/projects/${projectId}/nodes/${nodeId}/fields`, {
    method: 'PUT',
    body: JSON.stringify({ node_id: nodeId, fields }),
  })
}

/** 单条跨子图引用。 */
export interface CrossReferenceItem {
  edge_id: string
  other_node_id: string
  other_title: string
  other_section: 'plot' | 'character' | 'world'
  relation_type: string
  relation_label: string
  direction: 'outgoing' | 'incoming'
}

/** 节点在其他子图中的引用位置（first_revision 第 6 阶段）。 */
export interface CrossReferenceResponse {
  node_id: string
  section: 'plot' | 'character' | 'world' | null
  references: CrossReferenceItem[]
}

/** 更新节点字段（行内卡片“编辑”和节点详情页共用，复用图的 PATCH 节点端点）。 */
export async function updateNode(
  projectId: string,
  nodeId: string,
  patch: {
    title?: string
    content?: string
    tags?: string[]
    status?: string
    nodeType?: string
  },
): Promise<unknown> {
  return requestJson(`/api/projects/${projectId}/nodes/${nodeId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

/** 删除节点（聊天行内卡片“丢弃/撤销”使用）。 */
export async function deleteNode(projectId: string, nodeId: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}/nodes/${nodeId}`, { method: 'DELETE' })
}

export interface ProjectEdgePayload {
  id: string
  source: string
  target: string
  label?: string
  relationType?: string
  sourceHandle?: string | null
  targetHandle?: string | null
  type?: string
  animated?: boolean
}

/** 创建跨子图边（例如情节节点 → 角色节点）。 */
export async function createProjectEdge(
  projectId: string,
  edge: ProjectEdgePayload,
): Promise<ProjectEdgePayload> {
  return requestJson<ProjectEdgePayload>(`/api/projects/${projectId}/edges`, {
    method: 'POST',
    body: JSON.stringify({
      label: '',
      relationType: 'relates_to',
      type: 'bezier',
      animated: false,
      ...edge,
    }),
  })
}

/** 按 ID 删除单条边。 */
export async function deleteProjectEdge(projectId: string, edgeId: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}/edges/${edgeId}`, { method: 'DELETE' })
}

/** 读取节点的跨子图反向引用。 */
export async function getNodeCrossReferences(
  projectId: string,
  nodeId: string,
): Promise<CrossReferenceResponse> {
  return requestJson<CrossReferenceResponse>(
    `/api/projects/${projectId}/nodes/${nodeId}/cross_references`,
  )
}

/** 级联删除项目。 */
export async function deleteProject(projectId: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}`, { method: 'DELETE' })
}

/** 读取项目当前 seed；如果还没有 seed，后端会返回 404。 */
export async function getProjectSeed(projectId: string): Promise<ProjectSeed> {
  return requestJson<ProjectSeed>(`/api/projects/${projectId}/seed`)
}

/** 强制重建项目 seed，并递增版本号。 */
export async function rebuildProjectSeed(projectId: string): Promise<ProjectSeed> {
  return requestJson<ProjectSeed>(`/api/projects/${projectId}/seed/rebuild`, {
    method: 'POST',
  })
}
