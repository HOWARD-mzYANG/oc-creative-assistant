import { requestJson } from './http'

export interface RoleModelGpu {
  name: string
  memory_gb: number
  backend: string
  available: boolean
}

export interface RoleModelHardware {
  os: string
  python: string
  cpu_count: number
  ram_total_gb: number
  ram_available_gb: number
  disk_free_gb: number
  gpus: RoleModelGpu[]
  has_cuda: boolean
  can_train_lora: boolean
  notes: string[]
}

export interface RoleModelRecommendation {
  model_id: string
  display_name: string
  parameter_count_b: number
  quantization: string
  context_length: number
  estimated_vram_gb: number
  lora_rank: number
  lora_alpha: number
  batch_size: number
  gradient_accumulation_steps: number
  max_seq_length: number
  learning_rate: number
  download_url: string
  reason: string
  warnings: string[]
}

export interface RoleModelDatasetSample {
  id: string
  character_name: string
  instruction: string
  input: string
  output: string
  tags: string[]
  source_node_ids: string[]
  enabled: boolean
}

export interface RoleModelDataset {
  project_id: string
  samples: RoleModelDatasetSample[]
  updated_at: string | null
}

export interface RoleModelJob {
  status: string
  message: string
  progress: number
  model_id: string
  artifact_path: string
  started_at: string | null
  finished_at: string | null
  log: string[]
}

export interface RoleModelState {
  project_id: string
  hardware: RoleModelHardware | null
  recommendation: RoleModelRecommendation | null
  dataset_count: number
  dataset_updated_at: string | null
  download: RoleModelJob
  training: RoleModelJob
  adapter_ready: boolean
  local_runtime_ready: boolean
  runtime_warning: string
  chat_characters: string[]
}

export interface RoleModelChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface RoleModelChatHistoryItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode: string
  warning: string
  character_name: string
  cited_node_ids: string[]
  retrieved_context: Array<Record<string, unknown>>
  created_at: string | null
}

export interface RoleModelChatResponse {
  reply: string
  mode: 'local_lora' | 'api_fallback' | string
  cited_node_ids: string[]
  retrieved_context: Array<Record<string, unknown>>
  warning: string
}

export async function getRoleModelState(projectId: string): Promise<RoleModelState> {
  return requestJson<RoleModelState>(`/api/projects/${projectId}/role-model`)
}

export async function inspectRoleModelHardware(projectId: string): Promise<RoleModelHardware> {
  return requestJson<RoleModelHardware>(`/api/projects/${projectId}/role-model/hardware`)
}

export async function recommendRoleModel(
  projectId: string,
  payload: { preferred_model_id?: string | null; target_character?: string | null },
): Promise<RoleModelRecommendation> {
  return requestJson<RoleModelRecommendation>(`/api/projects/${projectId}/role-model/recommend`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getRoleModelDataset(projectId: string): Promise<RoleModelDataset> {
  return requestJson<RoleModelDataset>(`/api/projects/${projectId}/role-model/dataset`)
}

export async function generateRoleModelDataset(
  projectId: string,
  payload?: { samples_per_character?: number; max_samples?: number },
): Promise<RoleModelDataset> {
  return requestJson<RoleModelDataset>(`/api/projects/${projectId}/role-model/dataset/generate`, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  })
}

export async function saveRoleModelDataset(
  projectId: string,
  samples: RoleModelDatasetSample[],
): Promise<RoleModelDataset> {
  return requestJson<RoleModelDataset>(`/api/projects/${projectId}/role-model/dataset`, {
    method: 'PUT',
    body: JSON.stringify({ samples }),
  })
}

export async function startRoleModelDownload(
  projectId: string,
  modelId?: string | null,
): Promise<RoleModelJob> {
  return requestJson<RoleModelJob>(`/api/projects/${projectId}/role-model/download`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  })
}

export async function getRoleModelDownload(projectId: string): Promise<RoleModelJob> {
  return requestJson<RoleModelJob>(`/api/projects/${projectId}/role-model/download`)
}

export async function startRoleModelTraining(
  projectId: string,
  payload: {
    model_id?: string | null
    epochs?: number
    batch_size?: number | null
    gradient_accumulation_steps?: number | null
    lora_rank?: number | null
    lora_alpha?: number | null
    learning_rate?: number | null
    max_seq_length?: number | null
  },
): Promise<RoleModelJob> {
  return requestJson<RoleModelJob>(`/api/projects/${projectId}/role-model/train`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getRoleModelTraining(projectId: string): Promise<RoleModelJob> {
  return requestJson<RoleModelJob>(`/api/projects/${projectId}/role-model/train`)
}

function roleChatQuery(characterName: string): string {
  return `character_name=${encodeURIComponent(characterName)}`
}

export async function getRoleModelChatHistory(
  projectId: string,
  characterName: string,
): Promise<RoleModelChatHistoryItem[]> {
  return requestJson<RoleModelChatHistoryItem[]>(
    `/api/projects/${projectId}/role-model/chat?${roleChatQuery(characterName)}`,
  )
}

export async function clearRoleModelChatHistory(projectId: string, characterName: string): Promise<void> {
  await requestJson<void>(`/api/projects/${projectId}/role-model/chat?${roleChatQuery(characterName)}`, {
    method: 'DELETE',
  })
}

export async function chatWithRoleModel(
  projectId: string,
  payload: {
    message: string
    character_name?: string | null
    history: RoleModelChatMessage[]
  },
): Promise<RoleModelChatResponse> {
  return requestJson<RoleModelChatResponse>(`/api/projects/${projectId}/role-model/chat`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
