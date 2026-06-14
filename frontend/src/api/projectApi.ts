import type {
  ProjectCreatePayload,
  ProjectDetail,
  ProjectSeed,
  ProjectSummary,
} from '../types/project'
import { requestJson,backendBaseUrl } from './http'


/**
 * Project API client (first_revision phase 1).
 *
 * Maps to the backend /api/projects/*. Reading/writing sub-graph nodes/edges still goes through
 * graphApi's loadSubgraph / saveSubgraph (by graph_id).
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

/** Fetch the parsed project snapshot (used for PDF rendering). */
export async function getProjectExport(projectId: string): Promise<OcExport> {
  return requestJson<OcExport>(`/api/projects/${projectId}/export.oc`)
}

/** Download a lossless .oc snapshot of the project. */
export async function exportProjectOc(projectId: string): Promise<Blob> {
  const data = await requestJson<unknown>(`/api/projects/${projectId}/export.oc`)
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
}
/** 将 .oc 文件导入为新项目；返回新项目详情。 */
export async function importProjectOc(file: File): Promise<{ id: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${backendBaseUrl}/api/projects/import.oc`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`import failed: HTTP ${res.status}`)
  return res.json()
}

/** List all projects (project library cards). */
export async function listProjects(): Promise<ProjectSummary[]> {
  return requestJson<ProjectSummary[]>('/api/projects')
}

/** Create a project; the backend automatically creates three sub-graphs. */
export async function createProject(payload: ProjectCreatePayload): Promise<ProjectDetail> {
  return requestJson<ProjectDetail>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** Read project details (including the three graph_ids and the latest seed). */
export async function getProjectDetail(projectId: string): Promise<ProjectDetail> {
  return requestJson<ProjectDetail>(`/api/projects/${projectId}`)
}

/** Update the project name / description / cover image (used by the overview page to edit the summary). */
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

/** A single cross-sub-graph reference. */
export interface CrossReferenceItem {
  edge_id: string
  other_node_id: string
  other_title: string
  other_section: 'plot' | 'character' | 'world'
  relation_type: string
  relation_label: string
  direction: 'outgoing' | 'incoming'
}

/** Where a node is referenced in other sub-graphs (first_revision phase 6). */
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

/** Delete a node (used by the chat inline card "Reject/Undo"). */
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

/** Create a cross-sub-graph edge (e.g. plot node → character node). */
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

/** Remove a single edge by id. */
export async function deleteProjectEdge(projectId: string, edgeId: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}/edges/${edgeId}`, { method: 'DELETE' })
}

/** Read a node's cross-sub-graph back-references. */
export async function getNodeCrossReferences(
  projectId: string,
  nodeId: string,
): Promise<CrossReferenceResponse> {
  return requestJson<CrossReferenceResponse>(
    `/api/projects/${projectId}/nodes/${nodeId}/cross_references`,
  )
}

/** Cascade-delete a project. */
export async function deleteProject(projectId: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}`, { method: 'DELETE' })
}

/** Read the project's current seed; the backend returns 404 when no seed exists yet. */
export async function getProjectSeed(projectId: string): Promise<ProjectSeed> {
  return requestJson<ProjectSeed>(`/api/projects/${projectId}/seed`)
}

/** Force-rebuild the project seed, incrementing the version. */
export async function rebuildProjectSeed(projectId: string): Promise<ProjectSeed> {
  return requestJson<ProjectSeed>(`/api/projects/${projectId}/seed/rebuild`, {
    method: 'POST',
  })
}
