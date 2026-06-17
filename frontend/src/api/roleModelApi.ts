import { backendBaseUrl, requestJson } from './http'

export type RoleJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface RoleModelRelationDto {
  other_node_id: string
  other_title: string
  other_type: string
  relation_label: string
  relation_type: string
  direction: 'outgoing' | 'incoming'
  content: string
}

export interface RoleModelCrossReferenceDto {
  other_node_id: string
  other_title: string
  other_section: string
  relation_label: string
  relation_type: string
  direction: 'outgoing' | 'incoming'
  content: string
}

export interface RoleModelRelatedNodeDto {
  id: string
  title: string
  node_type: string
  content: string
  relation_label: string
}

export interface RoleModelSnapshotDto {
  project_id: string
  project_name: string
  character_id: string
  character_name: string
  character_summary: string
  fields: Record<string, string>
  tags: string[]
  relations: RoleModelRelationDto[]
  cross_references: RoleModelCrossReferenceDto[]
  related_nodes: RoleModelRelatedNodeDto[]
  project_seed: string
}

export interface RoleMaterialBriefDto {
  identity: string
  personality: string
  voice_style: string
  known_facts: string[]
  relationships: string[]
  world_context: string[]
  boundaries: string[]
  sample_plan: string[]
}

export interface RoleMaterialTraceItemDto {
  node: string
  title: string
  content: string
}

export interface RoleModelJobDto {
  id: string
  project_id: string
  character_id: string
  character_name: string
  status: RoleJobStatus
  sample_count: number
  dataset_path: string
  dataset_info_path: string
  train_config_path: string
  adapter_path: string
  material_brief_path: string
  log_tail: string
  error?: string | null
  created_at: string
  updated_at: string
}

export interface RoleModelOverviewDto {
  service_configured: boolean
  service_online: boolean
  service_error?: string | null
  snapshot: RoleModelSnapshotDto
  material_brief?: RoleMaterialBriefDto | null
  material_trace: RoleMaterialTraceItemDto[]
  jobs: RoleModelJobDto[]
  latest_job?: RoleModelJobDto | null
}

export interface RoleChatMessageDto {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface RoleChatLogItemDto extends RoleChatMessageDto {
  created_at: string
}

export type RoleChatStreamEvent =
  | { type: 'token'; text: string }
  | { type: 'status'; message: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export type RoleMaterialStreamEvent =
  | ({ type: 'trace_item' } & RoleMaterialTraceItemDto)
  | { type: 'material_brief'; brief: RoleMaterialBriefDto }
  | { type: 'done' }
  | { type: 'error'; message: string }

export async function getRoleModelOverview(
  projectId: string,
  characterId: string,
): Promise<RoleModelOverviewDto> {
  return requestJson<RoleModelOverviewDto>(
    `/api/projects/${projectId}/characters/${characterId}/role-model`,
  )
}

export async function startRoleModelTraining(
  projectId: string,
  characterId: string,
  sampleCount?: number,
): Promise<RoleModelJobDto> {
  return requestJson<RoleModelJobDto>(
    `/api/projects/${projectId}/characters/${characterId}/role-model/train`,
    {
      method: 'POST',
      body: JSON.stringify({ sample_count: sampleCount ?? null }),
    },
  )
}

export async function getRoleModelJob(
  projectId: string,
  characterId: string,
  jobId: string,
): Promise<RoleModelJobDto> {
  return requestJson<RoleModelJobDto>(
    `/api/projects/${projectId}/characters/${characterId}/role-model/jobs/${jobId}`,
  )
}

export async function getRoleChatHistory(
  projectId: string,
  characterId: string,
  jobId: string,
): Promise<RoleChatLogItemDto[]> {
  return requestJson<RoleChatLogItemDto[]>(
    `/api/projects/${projectId}/characters/${characterId}/role-model/jobs/${jobId}/chat-history`,
  )
}

export async function streamRoleMaterialBrief(
  projectId: string,
  characterId: string,
  onEvent: (event: RoleMaterialStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${backendBaseUrl}/api/projects/${projectId}/characters/${characterId}/role-model/material/stream`,
    { signal },
  )

  if (!response.ok || !response.body) {
    throw new Error(`资料 agent 请求失败：HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const raw of chunks) {
      const line = raw.trim()
      if (!line.startsWith('data: ')) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as RoleMaterialStreamEvent)
      } catch {
        /* Ignore broken SSE fragments. */
      }
    }
  }
}

export async function streamRoleChat(
  projectId: string,
  characterId: string,
  payload: {
    message: string
    job_id?: string | null
    history?: RoleChatMessageDto[]
  },
  onEvent: (event: RoleChatStreamEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${backendBaseUrl}/api/projects/${projectId}/characters/${characterId}/role-chat/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: payload.message,
        job_id: payload.job_id ?? null,
        history: payload.history ?? [],
      }),
    },
  )

  if (!response.ok || !response.body) {
    throw new Error(`角色对话请求失败：HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const raw of chunks) {
      const line = raw.trim()
      if (!line.startsWith('data: ')) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as RoleChatStreamEvent)
      } catch {
        /* Ignore broken SSE fragments. */
      }
    }
  }
}
