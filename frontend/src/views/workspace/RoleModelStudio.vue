<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  chatWithRoleModel,
  clearRoleModelChatHistory,
  generateRoleModelDataset,
  getRoleModelChatHistory,
  getRoleModelDataset,
  getRoleModelState,
  inspectRoleModelHardware,
  recommendRoleModel,
  saveRoleModelDataset,
  startRoleModelDownload,
  startRoleModelTraining,
  type RoleModelChatMessage,
  type RoleModelChatHistoryItem,
  type RoleModelDataset,
  type RoleModelJob,
  type RoleModelRecommendation,
  type RoleModelState,
} from '../../api/roleModelApi'

type ActionName =
  | ''
  | 'load'
  | 'hardware'
  | 'recommend'
  | 'generate'
  | 'save'
  | 'download'
  | 'train'
  | 'clear-chat'

interface StudioMessage {
  role: 'user' | 'assistant'
  content: string
  mode?: string
  warning?: string
}

type StudioMode = 'chat' | 'workflow'

const DATASET_PAGE_SIZE = 10
const MIN_TRAINING_SAMPLES = 200

const route = useRoute()
const projectId = computed(() => String(route.params.projectId ?? ''))

const state = ref<RoleModelState | null>(null)
const dataset = ref<RoleModelDataset>({ project_id: '', samples: [], updated_at: null })
const recommendation = ref<RoleModelRecommendation | null>(null)
const preferredModelId = ref('')
const targetCharacter = ref('')
const chatCharacter = ref('')
const chatInput = ref('')
const chatMessages = ref<StudioMessage[]>([])
const chatLog = ref<HTMLElement | null>(null)
const action = ref<ActionName>('')
const error = ref('')
const notice = ref('')
const studioMode = ref<StudioMode | null>(null)
const datasetDirty = ref(false)
const chatSending = ref(false)
const isRefreshing = ref(false)
const appliedRecommendationKey = ref('')
const datasetPage = ref(1)
const datasetGenerateForm = ref({
  samples_per_character: 64,
  max_samples: 500,
})

const trainForm = ref({
  epochs: 1,
  batch_size: null as number | null,
  gradient_accumulation_steps: null as number | null,
  lora_rank: null as number | null,
  lora_alpha: null as number | null,
  learning_rate: null as number | null,
  max_seq_length: null as number | null,
})

let pollTimer: ReturnType<typeof setInterval> | null = null

function emptyJob(): RoleModelJob {
  return {
    status: 'idle',
    message: '',
    progress: 0,
    model_id: '',
    artifact_path: '',
    started_at: null,
    finished_at: null,
    log: [],
  }
}

const hardware = computed(() => state.value?.hardware ?? null)
const downloadJob = computed(() => state.value?.download ?? emptyJob())
const trainingJob = computed(() => state.value?.training ?? emptyJob())
const isBusy = computed(() => Boolean(action.value) || chatSending.value)
const hasReadyRoleModel = computed(() => Boolean(state.value?.adapter_ready))
const localRuntimeReady = computed(() => Boolean(state.value?.local_runtime_ready))
const runtimeWarning = computed(() => state.value?.runtime_warning ?? '')
const isChatMode = computed(() => studioMode.value === 'chat' && hasReadyRoleModel.value)
const enabledSampleCount = computed(() => dataset.value.samples.filter((sample) => sample.enabled).length)
const datasetPageCount = computed(() =>
  Math.max(1, Math.ceil(dataset.value.samples.length / DATASET_PAGE_SIZE)),
)
const visibleDatasetSamples = computed(() => {
  const start = (datasetPage.value - 1) * DATASET_PAGE_SIZE
  return dataset.value.samples.slice(start, start + DATASET_PAGE_SIZE).map((sample, offset) => ({
    sample,
    index: start + offset,
  }))
})
const datasetRangeLabel = computed(() => {
  if (!dataset.value.samples.length) return '0 / 0'
  const start = (datasetPage.value - 1) * DATASET_PAGE_SIZE + 1
  const end = Math.min(dataset.value.samples.length, start + DATASET_PAGE_SIZE - 1)
  return `${start}-${end} / ${dataset.value.samples.length}`
})
const characterOptions = computed(() => {
  const names = dataset.value.samples
    .map((sample) => sample.character_name.trim())
    .filter(Boolean)
  return Array.from(new Set(names)).sort((a, b) => a.localeCompare(b))
})
const modelModeLabel = computed(() => {
  if (state.value?.adapter_ready && state.value.local_runtime_ready) return '本地 LoRA 已就绪'
  if (state.value?.adapter_ready) return '已训练，API 兜底'
  if (trainingJob.value.status === 'running') return 'LoRA 训练中'
  return 'API 风格兜底'
})
const modeDescription = computed(() =>
  isChatMode.value
    ? '已经检测到本地微调模型，当前页面默认进入角色模型聊天。需要重做数据或训练时，可以切回训练流程。'
    : '把项目角色设定整理成可编辑训练样本，再把小模型微调成专属口吻。',
)
const readyModelName = computed(
  () =>
    trainingJob.value.model_id ||
    downloadJob.value.model_id ||
    recommendation.value?.model_id ||
    '已训练角色模型',
)
const selectedModelId = computed(() => preferredModelId.value.trim() || recommendation.value?.model_id || '')
const downloadedSelectedModel = computed(
  () =>
    Boolean(selectedModelId.value) &&
    downloadJob.value.status === 'completed' &&
    Boolean(downloadJob.value.artifact_path) &&
    downloadJob.value.model_id === selectedModelId.value,
)
const modelScopeUrl = computed(() => {
  const modelId = selectedModelId.value
  if (modelId.includes('/')) return `https://modelscope.cn/models/${modelId}/summary`
  return recommendation.value?.download_url || ''
})
const canDownload = computed(
  () => Boolean(selectedModelId.value) && !downloadedSelectedModel.value && !isActiveJob(downloadJob.value),
)
const hardwareCanTrain = computed(() => hardware.value?.can_train_lora ?? true)
const canTrain = computed(
  () =>
    enabledSampleCount.value >= MIN_TRAINING_SAMPLES &&
    downloadedSelectedModel.value &&
    hardwareCanTrain.value &&
    !isActiveJob(trainingJob.value),
)
const hasActiveJob = computed(() => isActiveJob(downloadJob.value) || isActiveJob(trainingJob.value))
const downloadButtonLabel = computed(() => (downloadedSelectedModel.value ? '已下载' : '下载模型'))
const trainingReadinessMessage = computed(() => {
  if (isActiveJob(trainingJob.value)) return '训练任务正在进行中。'
  if (!selectedModelId.value) return '请先生成推荐或填写 ModelScope 模型 ID。'
  if (enabledSampleCount.value < MIN_TRAINING_SAMPLES) {
    return `至少需要 ${MIN_TRAINING_SAMPLES} 条启用样本，当前只有 ${enabledSampleCount.value} 条。`
  }
  if (!downloadedSelectedModel.value) return '请先下载当前模型 ID 对应的基础模型。'
  if (!hardwareCanTrain.value) {
    const notes = hardware.value?.notes?.filter(Boolean).join('；')
    return notes ? `当前后端机器不能本地训练：${notes}` : '当前后端机器不能本地训练 LoRA。'
  }
  return '训练前置条件已满足。'
})
const chatBadgeLabel = computed(() => (localRuntimeReady.value ? 'local_lora' : 'api_fallback'))

function isActiveJob(job: RoleModelJob): boolean {
  return ['queued', 'running', 'starting'].includes(job.status)
}

function percent(job: RoleModelJob): number {
  return Math.round(Math.max(0, Math.min(Number(job.progress || 0), 1)) * 100)
}

function statusTone(status: string): string {
  if (status === 'completed') return 'is-completed'
  if (status === 'failed') return 'is-failed'
  if (status === 'blocked') return 'is-blocked'
  if (isActiveJob({ ...emptyJob(), status })) return 'is-running'
  return 'is-idle'
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    idle: '未开始',
    queued: '排队中',
    running: '进行中',
    starting: '启动中',
    completed: '已完成',
    failed: '失败',
    blocked: '已阻止',
  }
  return labels[status] ?? status
}

function applyInitialStudioMode(nextState: RoleModelState): void {
  if (studioMode.value === null) {
    studioMode.value = nextState.adapter_ready ? 'chat' : 'workflow'
    return
  }
  if (studioMode.value === 'chat' && !nextState.adapter_ready) {
    studioMode.value = 'workflow'
  }
}

function openTrainingWorkflow(): void {
  studioMode.value = 'workflow'
  notice.value = '已切换到新训练流程'
}

function openChatMode(): void {
  if (!hasReadyRoleModel.value) return
  studioMode.value = 'chat'
  notice.value = ''
  scrollChat()
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '尚未更新'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function parseError(errorLike: unknown): string {
  return errorLike instanceof Error ? errorLike.message : String(errorLike)
}

function historyItemToStudioMessage(item: RoleModelChatHistoryItem): StudioMessage {
  return {
    role: item.role,
    content: item.content,
    mode: item.mode || undefined,
    warning: item.warning || undefined,
  }
}

function clampInteger(value: number, min: number, max: number, fallback: number): number {
  const next = Math.round(Number(value))
  if (!Number.isFinite(next)) return fallback
  return Math.max(min, Math.min(next, max))
}

function datasetGenerationPayload(): { samples_per_character: number; max_samples: number } {
  const samplesPerCharacter = clampInteger(datasetGenerateForm.value.samples_per_character, 8, 240, 64)
  const maxSamples = clampInteger(datasetGenerateForm.value.max_samples, MIN_TRAINING_SAMPLES, 800, 500)
  datasetGenerateForm.value.samples_per_character = samplesPerCharacter
  datasetGenerateForm.value.max_samples = maxSamples
  return {
    samples_per_character: samplesPerCharacter,
    max_samples: maxSamples,
  }
}

function applyRecommendation(next: RoleModelRecommendation | null): void {
  recommendation.value = next
  if (!next) return
  const key = [
    next.model_id,
    next.batch_size,
    next.gradient_accumulation_steps,
    next.lora_rank,
    next.lora_alpha,
    next.learning_rate,
    next.max_seq_length,
  ].join(':')
  if (appliedRecommendationKey.value === key) return
  appliedRecommendationKey.value = key
  trainForm.value = {
    epochs: trainForm.value.epochs || 1,
    batch_size: next.batch_size,
    gradient_accumulation_steps: next.gradient_accumulation_steps,
    lora_rank: next.lora_rank,
    lora_alpha: next.lora_alpha,
    learning_rate: next.learning_rate,
    max_seq_length: next.max_seq_length,
  }
}

function syncRecommendedModelInput(next: RoleModelRecommendation | null): void {
  if (!next) return
  preferredModelId.value = next.model_id
}

async function runAction(name: ActionName, task: () => Promise<void>): Promise<void> {
  if (action.value) return
  action.value = name
  error.value = ''
  notice.value = ''
  try {
    await task()
  } catch (caught) {
    error.value = parseError(caught)
  } finally {
    action.value = ''
  }
}

async function refreshState(): Promise<void> {
  if (!projectId.value || isRefreshing.value) return
  isRefreshing.value = true
  try {
    const next = await getRoleModelState(projectId.value)
    state.value = next
    applyInitialStudioMode(next)
    applyRecommendation(next.recommendation)
    if (!preferredModelId.value.trim()) {
      syncRecommendedModelInput(next.recommendation)
    }
  } catch (caught) {
    error.value = parseError(caught)
  } finally {
    isRefreshing.value = false
  }
}

async function loadChatHistory(): Promise<void> {
  if (!projectId.value) return
  const history = await getRoleModelChatHistory(projectId.value)
  chatMessages.value = history.map(historyItemToStudioMessage)
  scrollChat()
}

async function loadAll(): Promise<void> {
  await runAction('load', async () => {
    const [nextState, nextDataset, nextChatHistory] = await Promise.all([
      getRoleModelState(projectId.value),
      getRoleModelDataset(projectId.value),
      getRoleModelChatHistory(projectId.value),
    ])
    state.value = nextState
    applyInitialStudioMode(nextState)
    dataset.value = nextDataset
    chatMessages.value = nextChatHistory.map(historyItemToStudioMessage)
    datasetPage.value = 1
    datasetDirty.value = false
    applyRecommendation(nextState.recommendation)
    if (!preferredModelId.value.trim()) {
      syncRecommendedModelInput(nextState.recommendation)
    }
    scrollChat()
  })
}

async function detectHardware(): Promise<void> {
  await runAction('hardware', async () => {
    const result = await inspectRoleModelHardware(projectId.value)
    if (state.value) {
      state.value = { ...state.value, hardware: result }
    }
    notice.value = '硬件检测已更新'
  })
}

async function recommendModel(): Promise<void> {
  await runAction('recommend', async () => {
    const result = await recommendRoleModel(projectId.value, {
      preferred_model_id: preferredModelId.value.trim() || null,
      target_character: targetCharacter.value.trim() || null,
    })
    syncRecommendedModelInput(result)
    applyRecommendation(result)
    await refreshState()
    notice.value = '已生成模型和训练参数建议'
  })
}

async function generateDataset(): Promise<void> {
  await runAction('generate', async () => {
    const payload = datasetGenerationPayload()
    dataset.value = await generateRoleModelDataset(projectId.value, payload)
    datasetPage.value = 1
    datasetDirty.value = false
    await refreshState()
    notice.value = `已生成 ${dataset.value.samples.length} 条可编辑样本`
  })
}

async function saveDataset(): Promise<void> {
  await runAction('save', async () => {
    await saveDatasetToServer()
    await refreshState()
    notice.value = '数据集已保存'
  })
}

async function saveDatasetToServer(): Promise<void> {
  dataset.value = await saveRoleModelDataset(projectId.value, dataset.value.samples)
  datasetPage.value = Math.min(datasetPage.value, datasetPageCount.value)
  datasetDirty.value = false
}

async function downloadModel(): Promise<void> {
  await runAction('download', async () => {
    const job = await startRoleModelDownload(
      projectId.value,
      preferredModelId.value.trim() || recommendation.value?.model_id || null,
    )
    if (state.value) state.value = { ...state.value, download: job }
    notice.value = '下载任务已启动'
  })
}

async function trainModel(): Promise<void> {
  await runAction('train', async () => {
    if (datasetDirty.value) {
      await saveDatasetToServer()
    }
    const job = await startRoleModelTraining(projectId.value, {
      model_id: selectedModelId.value || null,
      epochs: Number(trainForm.value.epochs || 1),
      batch_size: nullableNumber(trainForm.value.batch_size),
      gradient_accumulation_steps: nullableNumber(trainForm.value.gradient_accumulation_steps),
      lora_rank: nullableNumber(trainForm.value.lora_rank),
      lora_alpha: nullableNumber(trainForm.value.lora_alpha),
      learning_rate: nullableNumber(trainForm.value.learning_rate),
      max_seq_length: nullableNumber(trainForm.value.max_seq_length),
    })
    if (state.value) state.value = { ...state.value, training: job }
    notice.value = '训练任务已启动'
  })
}

function nullableNumber(value: number | null): number | null {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null
  return Number(value)
}

function markDirty(): void {
  datasetDirty.value = true
}

function addSample(): void {
  dataset.value.samples.unshift({
    id: `sample-${Date.now()}`,
    character_name: chatCharacter.value || targetCharacter.value || '',
    instruction: '',
    input: '',
    output: '',
    tags: [],
    source_node_ids: [],
    enabled: true,
  })
  datasetPage.value = 1
  datasetDirty.value = true
}

function removeSample(index: number): void {
  dataset.value.samples.splice(index, 1)
  datasetPage.value = Math.min(datasetPage.value, datasetPageCount.value)
  datasetDirty.value = true
}

function previousDatasetPage(): void {
  datasetPage.value = Math.max(1, datasetPage.value - 1)
}

function nextDatasetPage(): void {
  datasetPage.value = Math.min(datasetPageCount.value, datasetPage.value + 1)
}

async function sendChat(): Promise<void> {
  const message = chatInput.value.trim()
  if (!message || chatSending.value) return
  const history: RoleModelChatMessage[] = chatMessages.value.map((item) => ({
    role: item.role,
    content: item.content,
  }))
  chatMessages.value.push({ role: 'user', content: message })
  chatInput.value = ''
  chatSending.value = true
  error.value = ''
  scrollChat()
  try {
    const response = await chatWithRoleModel(projectId.value, {
      message,
      character_name: chatCharacter.value.trim() || null,
      history,
    })
    chatMessages.value.push({
      role: 'assistant',
      content: response.reply,
      mode: response.mode,
      warning: response.warning,
    })
    try {
      await loadChatHistory()
    } catch (caught) {
      notice.value = `角色模型已回复，但刷新聊天记录失败：${parseError(caught)}`
    }
  } catch (caught) {
    chatMessages.value.push({
      role: 'assistant',
      content: `角色模型暂时没有回应：${parseError(caught)}`,
      mode: 'error',
    })
  } finally {
    chatSending.value = false
    scrollChat()
  }
}

async function clearChat(): Promise<void> {
  await runAction('clear-chat', async () => {
    await clearRoleModelChatHistory(projectId.value)
    chatMessages.value = []
    notice.value = '角色模型聊天记录已清空'
  })
}

function scrollChat(): void {
  void nextTick(() => {
    const el = chatLog.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  })
}

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    void refreshState()
  }, 2500)
}

function stopPolling(): void {
  if (!pollTimer) return
  clearInterval(pollTimer)
  pollTimer = null
}

watch(hasActiveJob, (active) => {
  if (active) startPolling()
  else stopPolling()
})

watch(
  () => projectId.value,
  () => {
    stopPolling()
    studioMode.value = null
    void loadAll()
  },
)

watch(datasetPageCount, (count) => {
  datasetPage.value = Math.min(datasetPage.value, count)
})

onMounted(() => {
  void loadAll()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <section class="role-model">
    <header class="role-model__header">
      <div class="role-model__title-block">
        <span class="eyebrow">Local Role Model</span>
        <h2>{{ isChatMode ? '角色模型聊天' : '角色模型工作台' }}</h2>
        <p>{{ modeDescription }}</p>
      </div>
      <div class="role-model__header-actions">
        <button
          v-if="hasReadyRoleModel && !isChatMode"
          type="button"
          class="role-model__button"
          :disabled="isBusy"
          @click="openChatMode"
        >
          回到聊天
        </button>
        <button
          v-if="hasReadyRoleModel && isChatMode"
          type="button"
          class="role-model__button"
          :disabled="isBusy"
          @click="openTrainingWorkflow"
        >
          新训练模型
        </button>
        <div class="role-model__mode" :class="{ 'is-ready': state?.adapter_ready }">
          <span class="role-model__mode-dot" />
          <span>{{ modelModeLabel }}</span>
        </div>
      </div>
    </header>

    <p v-if="error" class="role-model__alert">{{ error }}</p>
    <p v-if="notice" class="role-model__notice">{{ notice }}</p>

    <div class="role-model__layout" :class="{ 'role-model__layout--chat-first': isChatMode }">
      <div v-if="!isChatMode" class="role-model__rail">
        <section class="role-model__panel">
          <div class="role-model__panel-head">
            <div>
              <span class="role-model__kicker">Step 1</span>
              <h3>模型推荐</h3>
            </div>
            <button type="button" class="role-model__button" :disabled="isBusy" @click="detectHardware">
              检测硬件
            </button>
          </div>

          <div class="role-model__metrics">
            <div>
              <span>系统</span>
              <strong>{{ hardware?.os || '未检测' }}</strong>
            </div>
            <div>
              <span>内存</span>
              <strong>{{ hardware ? `${hardware.ram_total_gb} GB` : '未检测' }}</strong>
            </div>
            <div>
              <span>磁盘</span>
              <strong>{{ hardware ? `${hardware.disk_free_gb} GB` : '未检测' }}</strong>
            </div>
            <div>
              <span>CUDA</span>
              <strong>{{ hardware?.has_cuda ? '可用' : '未就绪' }}</strong>
            </div>
          </div>

          <div v-if="hardware?.gpus.length" class="role-model__gpu-list">
            <div v-for="gpu in hardware.gpus" :key="`${gpu.backend}-${gpu.name}`">
              <span>{{ gpu.name }}</span>
              <strong>{{ gpu.memory_gb }} GB</strong>
            </div>
          </div>

          <ul v-if="hardware?.notes.length" class="role-model__notes">
            <li v-for="note in hardware.notes" :key="note">{{ note }}</li>
          </ul>

          <label class="role-model__field">
            <span>ModelScope 模型 ID</span>
            <input v-model.trim="preferredModelId" type="text" placeholder="推荐后会自动填入，例如 Qwen/Qwen3-1.7B" />
          </label>
          <label class="role-model__field">
            <span>目标角色</span>
            <input v-model.trim="targetCharacter" type="text" placeholder="不填则按全项目推荐" />
          </label>
          <button
            type="button"
            class="role-model__button role-model__button--primary"
            :disabled="isBusy"
            @click="recommendModel"
          >
            生成推荐
          </button>

          <div v-if="recommendation" class="role-model__recommendation">
            <p>{{ recommendation.reason }}</p>
            <dl>
              <div>
                <dt>参数量</dt>
                <dd>{{ recommendation.parameter_count_b }}B</dd>
              </div>
              <div>
                <dt>显存估计</dt>
                <dd>{{ recommendation.estimated_vram_gb }} GB</dd>
              </div>
              <div>
                <dt>序列长度</dt>
                <dd>{{ recommendation.max_seq_length }}</dd>
              </div>
            </dl>
            <ul v-if="recommendation.warnings.length" class="role-model__notes">
              <li v-for="warning in recommendation.warnings" :key="warning">{{ warning }}</li>
            </ul>
            <a v-if="modelScopeUrl" :href="modelScopeUrl" target="_blank" rel="noreferrer">打开 ModelScope</a>
          </div>
        </section>

        <section class="role-model__panel">
          <div class="role-model__panel-head">
            <div>
              <span class="role-model__kicker">Step 3</span>
              <h3>下载与微调</h3>
            </div>
          </div>

          <div class="role-model__actions">
            <button
              type="button"
              class="role-model__button"
              :disabled="!canDownload || isBusy"
              @click="downloadModel"
            >
              {{ downloadButtonLabel }}
            </button>
            <button
              type="button"
              class="role-model__button role-model__button--primary"
              :disabled="!canTrain || isBusy"
              @click="trainModel"
            >
              开始训练
            </button>
          </div>
          <p
            class="role-model__readiness"
            :class="{ 'is-ready': canTrain, 'is-blocked': !canTrain }"
          >
            {{ trainingReadinessMessage }}
          </p>

          <div class="role-model__train-grid">
            <label>
              <span>Epoch</span>
              <input v-model.number="trainForm.epochs" type="number" min="0.1" max="5" step="0.1" />
            </label>
            <label>
              <span>Batch</span>
              <input v-model.number="trainForm.batch_size" type="number" min="1" max="8" />
            </label>
            <label>
              <span>Rank</span>
              <input v-model.number="trainForm.lora_rank" type="number" min="4" max="64" />
            </label>
            <label>
              <span>Alpha</span>
              <input v-model.number="trainForm.lora_alpha" type="number" min="8" max="128" />
            </label>
          </div>

          <div class="role-model__job">
            <div class="role-model__job-head">
              <strong>下载</strong>
              <span :class="['role-model__job-state', statusTone(downloadJob.status)]">
                {{ statusLabel(downloadJob.status) }}
              </span>
            </div>
            <div class="role-model__progress"><span :style="{ width: `${percent(downloadJob)}%` }" /></div>
            <p>{{ downloadJob.message || '等待模型下载' }}</p>
          </div>

          <div class="role-model__job">
            <div class="role-model__job-head">
              <strong>训练</strong>
              <span :class="['role-model__job-state', statusTone(trainingJob.status)]">
                {{ statusLabel(trainingJob.status) }}
              </span>
            </div>
            <div class="role-model__progress"><span :style="{ width: `${percent(trainingJob)}%` }" /></div>
            <p>{{ trainingJob.message || '等待 LoRA 训练' }}</p>
          </div>

          <div v-if="trainingJob.log.length || downloadJob.log.length" class="role-model__log">
            <span>最近日志</span>
            <p v-for="line in [...downloadJob.log, ...trainingJob.log].slice(-6)" :key="line">{{ line }}</p>
          </div>
        </section>
      </div>

      <div class="role-model__work">
        <section v-if="!isChatMode" class="role-model__panel role-model__dataset">
          <div class="role-model__panel-head">
            <div>
              <span class="role-model__kicker">Step 2</span>
              <h3>LoRA 数据集</h3>
            </div>
            <div class="role-model__dataset-actions">
              <button type="button" class="role-model__button" :disabled="isBusy" @click="addSample">
                新增样本
              </button>
              <button type="button" class="role-model__button" :disabled="isBusy" @click="generateDataset">
                AI 生成
              </button>
              <button
                type="button"
                class="role-model__button role-model__button--primary"
                :disabled="isBusy || !datasetDirty"
                @click="saveDataset"
              >
                保存
              </button>
            </div>
          </div>

          <div class="role-model__dataset-controls">
            <label class="role-model__field role-model__field--compact">
              <span>每角色目标</span>
              <input
                v-model.number="datasetGenerateForm.samples_per_character"
                type="number"
                min="8"
                max="240"
                step="4"
              />
            </label>
            <label class="role-model__field role-model__field--compact">
              <span>最多样本</span>
              <input
                v-model.number="datasetGenerateForm.max_samples"
                type="number"
                min="200"
                max="800"
                step="50"
              />
            </label>
          </div>

          <div class="role-model__dataset-meta">
            <span>{{ enabledSampleCount }} / {{ dataset.samples.length }} 条启用</span>
            <span :class="{ 'is-dirty': enabledSampleCount < MIN_TRAINING_SAMPLES }">
              训练门槛 {{ MIN_TRAINING_SAMPLES }} 条
            </span>
            <span>当前 {{ datasetRangeLabel }}</span>
            <span>更新于 {{ formatTime(dataset.updated_at) }}</span>
            <span v-if="datasetDirty" class="is-dirty">有未保存修改</span>
          </div>

          <div v-if="dataset.samples.length > DATASET_PAGE_SIZE" class="role-model__pager">
            <button type="button" class="role-model__button" :disabled="datasetPage <= 1" @click="previousDatasetPage">
              上一页
            </button>
            <span>第 {{ datasetPage }} / {{ datasetPageCount }} 页</span>
            <button
              type="button"
              class="role-model__button"
              :disabled="datasetPage >= datasetPageCount"
              @click="nextDatasetPage"
            >
              下一页
            </button>
          </div>

          <div v-if="!dataset.samples.length" class="role-model__empty">
            还没有训练样本。
          </div>
          <div v-else class="role-model__samples">
            <article v-for="{ sample, index } in visibleDatasetSamples" :key="sample.id" class="role-model__sample">
              <div class="role-model__sample-head">
                <label class="role-model__sample-toggle">
                  <input v-model="sample.enabled" type="checkbox" @change="markDirty" />
                  <span>启用</span>
                </label>
                <input
                  v-model="sample.character_name"
                  class="role-model__sample-name"
                  type="text"
                  placeholder="角色名"
                  @input="markDirty"
                />
                <button type="button" class="role-model__button role-model__button--ghost" @click="removeSample(index)">
                  删除
                </button>
              </div>

              <label class="role-model__sample-field">
                <span>用户问题</span>
                <textarea v-model="sample.instruction" rows="2" @input="markDirty" />
              </label>
              <label class="role-model__sample-field">
                <span>附加上下文</span>
                <textarea v-model="sample.input" rows="2" placeholder="可为空" @input="markDirty" />
              </label>
              <label class="role-model__sample-field">
                <span>角色回答</span>
                <textarea v-model="sample.output" rows="4" @input="markDirty" />
              </label>
            </article>
          </div>
        </section>

        <section class="role-model__panel role-model__chat" :class="{ 'role-model__chat--primary': isChatMode }">
          <div class="role-model__panel-head">
            <div>
              <span class="role-model__kicker">{{ isChatMode ? 'Ready' : 'Step 4' }}</span>
              <h3>角色模型聊天</h3>
            </div>
            <button
              type="button"
              class="role-model__button role-model__button--ghost"
              :disabled="isBusy || !chatMessages.length"
              @click="clearChat"
            >
              清空
            </button>
          </div>

          <div class="role-model__chat-controls">
            <label class="role-model__field">
              <span>当前角色</span>
              <input v-model.trim="chatCharacter" list="role-model-characters" placeholder="可从数据集角色中选择" />
              <datalist id="role-model-characters">
                <option v-for="name in characterOptions" :key="name" :value="name" />
              </datalist>
            </label>
            <div
              class="role-model__chat-badge"
              :class="{ 'is-ready': localRuntimeReady, 'is-fallback': hasReadyRoleModel && !localRuntimeReady }"
            >
              {{ chatBadgeLabel }}
            </div>
          </div>
          <p v-if="runtimeWarning && hasReadyRoleModel" class="role-model__runtime-warning">
            {{ runtimeWarning }}
          </p>

          <div ref="chatLog" class="role-model__chat-log">
            <p v-if="!chatMessages.length" class="role-model__empty">对话会在这里开始。</p>
            <article
              v-for="(message, index) in chatMessages"
              :key="`${message.role}-${index}`"
              class="role-model__message"
              :class="`is-${message.role}`"
            >
              <span>{{ message.role === 'user' ? '你' : '角色模型' }}</span>
              <p>{{ message.content }}</p>
              <small v-if="message.mode">{{ message.mode }}</small>
              <small v-if="message.warning">{{ message.warning }}</small>
            </article>
            <article v-if="chatSending" class="role-model__message is-assistant">
              <span>角色模型</span>
              <p>正在组织回答...</p>
            </article>
          </div>

          <form class="role-model__composer" @submit.prevent="sendChat">
            <input v-model="chatInput" type="text" placeholder="和微调角色模型聊一句" />
            <button type="submit" class="role-model__button role-model__button--primary" :disabled="chatSending || !chatInput.trim()">
              发送
            </button>
          </form>
        </section>
      </div>

      <aside v-if="isChatMode" class="role-model__panel role-model__ready-summary">
        <span class="role-model__kicker">Model Status</span>
        <h3>已加载上次训练结果</h3>
        <dl>
          <div>
            <dt>模型</dt>
            <dd>{{ readyModelName }}</dd>
          </div>
          <div>
            <dt>样本</dt>
            <dd>{{ state?.dataset_count ?? dataset.samples.length }} 条</dd>
          </div>
          <div>
            <dt>Adapter</dt>
            <dd>{{ hasReadyRoleModel ? '训练产物已找到' : '尚未训练完成' }}</dd>
          </div>
          <div>
            <dt>运行模式</dt>
            <dd>{{ chatBadgeLabel }}</dd>
          </div>
          <div>
            <dt>聊天记录</dt>
            <dd>{{ chatMessages.length }} 条</dd>
          </div>
        </dl>
        <button
          type="button"
          class="role-model__button role-model__button--primary"
          :disabled="isBusy"
          @click="openTrainingWorkflow"
        >
          新训练模型
        </button>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.role-model {
  --role-accent: #0f766e;
  --role-accent-soft: rgba(15, 118, 110, 0.11);
  --role-accent-border: rgba(15, 118, 110, 0.34);
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background:
    linear-gradient(180deg, rgba(15, 118, 110, 0.06), transparent 210px),
    var(--app-bg);
}

.role-model__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.role-model__title-block {
  min-width: 0;
}

.role-model__title-block h2 {
  margin: 4px 0 6px;
  font-size: 1.55rem;
  line-height: 1.2;
}

.role-model__title-block p {
  margin: 0;
  max-width: 680px;
  color: var(--text-soft);
  line-height: 1.55;
  font-size: 0.92rem;
}

.role-model__header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.role-model__mode {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel);
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 700;
}

.role-model__mode.is-ready {
  border-color: var(--role-accent-border);
  color: var(--role-accent);
  background: var(--role-accent-soft);
}

.role-model__mode-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.role-model__alert,
.role-model__notice {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 0.86rem;
  line-height: 1.45;
}

.role-model__alert {
  border: 1px solid rgba(190, 18, 60, 0.26);
  background: rgba(255, 241, 242, 0.82);
  color: #9f1239;
}

.role-model__notice {
  border: 1px solid var(--role-accent-border);
  background: var(--role-accent-soft);
  color: var(--role-accent);
}

.role-model__layout {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(290px, 360px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.role-model__layout--chat-first {
  grid-template-columns: minmax(0, 1fr) minmax(250px, 340px);
}

.role-model__rail,
.role-model__work {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.role-model__panel {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  padding: 15px;
}

.role-model__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 13px;
}

.role-model__panel-head h3 {
  margin: 2px 0 0;
  font-size: 1.05rem;
  line-height: 1.25;
}

.role-model__kicker {
  display: block;
  color: var(--role-accent);
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.role-model__button {
  flex-shrink: 0;
  min-height: 32px;
  padding: 0 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--panel);
  color: var(--text-soft);
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 700;
}

.role-model__button:hover:not(:disabled) {
  border-color: var(--role-accent-border);
  color: var(--role-accent);
  background: var(--role-accent-soft);
}

.role-model__button--primary {
  border-color: var(--role-accent);
  color: #fff;
  background: var(--role-accent);
}

.role-model__button--primary:hover:not(:disabled) {
  border-color: #115e59;
  background: #115e59;
  color: #fff;
}

.role-model__button--ghost {
  border-color: transparent;
  background: transparent;
}

.role-model__button:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.role-model__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.role-model__metrics div,
.role-model__gpu-list div {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fbfbfa;
}

.role-model__metrics span,
.role-model__gpu-list span,
.role-model__field span,
.role-model__train-grid span,
.role-model__sample-field span,
.role-model__log span {
  display: block;
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.role-model__metrics strong,
.role-model__gpu-list strong {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.88rem;
}

.role-model__gpu-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.role-model__gpu-list div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.role-model__notes {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #92400e;
  font-size: 0.82rem;
  line-height: 1.5;
}

.role-model__field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 12px;
}

.role-model__field--compact {
  width: min(160px, 100%);
  margin-top: 0;
}

.role-model__field input,
.role-model__train-grid input,
.role-model__sample-name,
.role-model__sample-field textarea,
.role-model__composer input {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text);
}

.role-model__field input,
.role-model__train-grid input,
.role-model__sample-name,
.role-model__composer input {
  height: 34px;
  padding: 0 10px;
}

.role-model__recommendation {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.role-model__recommendation strong,
.role-model__recommendation code {
  display: block;
  overflow-wrap: anywhere;
}

.role-model__recommendation code {
  margin-top: 4px;
  color: var(--role-accent);
  font-size: 0.78rem;
}

.role-model__recommendation p {
  color: var(--text-soft);
  font-size: 0.84rem;
  line-height: 1.5;
}

.role-model__recommendation dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0;
}

.role-model__recommendation dt,
.role-model__recommendation dd {
  margin: 0;
}

.role-model__recommendation dt {
  color: var(--muted);
  font-size: 0.7rem;
}

.role-model__recommendation dd {
  font-weight: 800;
}

.role-model__recommendation a {
  color: var(--role-accent);
  font-size: 0.84rem;
  font-weight: 800;
  text-decoration: none;
}

.role-model__actions,
.role-model__dataset-actions,
.role-model__composer,
.role-model__chat-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.role-model__readiness,
.role-model__runtime-warning {
  margin: 10px 0 0;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  line-height: 1.45;
}

.role-model__readiness.is-ready {
  border: 1px solid var(--role-accent-border);
  background: var(--role-accent-soft);
  color: var(--role-accent);
}

.role-model__readiness.is-blocked,
.role-model__runtime-warning {
  border: 1px solid rgba(146, 64, 14, 0.22);
  background: rgba(255, 251, 235, 0.8);
  color: #92400e;
}

.role-model__train-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0;
}

.role-model__job {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 12px;
}

.role-model__job-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.role-model__job-state {
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.72rem;
  font-weight: 800;
  background: #f5f5f4;
  color: var(--muted);
}

.role-model__job-state.is-running {
  background: var(--role-accent-soft);
  color: var(--role-accent);
}

.role-model__job-state.is-completed {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.role-model__job-state.is-failed,
.role-model__job-state.is-blocked {
  background: rgba(190, 18, 60, 0.1);
  color: #9f1239;
}

.role-model__progress {
  height: 7px;
  margin: 9px 0;
  border-radius: 999px;
  background: #ece9e3;
  overflow: hidden;
}

.role-model__progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--role-accent);
  transition: width 0.18s ease;
}

.role-model__job p,
.role-model__log p {
  margin: 0;
  color: var(--text-soft);
  font-size: 0.8rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.role-model__log {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.role-model__log p + p {
  margin-top: 6px;
}

.role-model__dataset {
  min-height: 380px;
}

.role-model__dataset-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.role-model__dataset-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.role-model__dataset-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 0.8rem;
}

.role-model__pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.role-model__dataset-meta .is-dirty {
  color: #92400e;
  font-weight: 800;
}

.role-model__empty {
  margin: 0;
  padding: 18px 0;
  color: var(--muted);
  font-size: 0.88rem;
  text-align: center;
}

.role-model__samples {
  max-height: min(66vh, 760px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  padding-right: 6px;
  border-top: 1px solid var(--border);
}

.role-model__sample {
  padding: 14px 0;
  border-top: 1px solid var(--border);
}

.role-model__sample:first-child {
  border-top: none;
}

.role-model__sample-head {
  display: grid;
  grid-template-columns: auto minmax(140px, 260px) auto;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.role-model__sample-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-soft);
  font-size: 0.82rem;
  font-weight: 800;
}

.role-model__sample-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 8px;
}

.role-model__sample-field textarea {
  min-height: 58px;
  padding: 9px 10px;
  line-height: 1.5;
  resize: vertical;
}

.role-model__sample-field:last-child textarea {
  min-height: 110px;
}

.role-model__chat {
  min-height: 420px;
  display: flex;
  flex-direction: column;
}

.role-model__chat--primary {
  min-height: min(72vh, 760px);
}

.role-model__chat-controls {
  align-items: flex-end;
  margin-bottom: 10px;
}

.role-model__chat-controls .role-model__field {
  flex: 1;
  margin-top: 0;
}

.role-model__chat-badge {
  flex-shrink: 0;
  height: 34px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(120, 113, 108, 0.22);
  background: #f5f5f4;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 800;
}

.role-model__chat-badge.is-ready {
  border-color: var(--role-accent-border);
  background: var(--role-accent-soft);
  color: var(--role-accent);
}

.role-model__chat-badge.is-fallback {
  border-color: rgba(146, 64, 14, 0.28);
  background: rgba(255, 251, 235, 0.8);
  color: #92400e;
}

.role-model__chat-log {
  min-height: 260px;
  max-height: 480px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fbfbfa;
}

.role-model__chat--primary .role-model__chat-log {
  min-height: 420px;
  max-height: min(58vh, 620px);
}

.role-model__message {
  max-width: min(78%, 720px);
  padding: 10px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
  box-shadow: var(--shadow-sm);
}

.role-model__message.is-user {
  align-self: flex-end;
  border-color: var(--role-accent-border);
  background: var(--role-accent-soft);
}

.role-model__message.is-assistant {
  align-self: flex-start;
}

.role-model__message span {
  display: block;
  margin-bottom: 4px;
  color: var(--muted);
  font-size: 0.7rem;
  font-weight: 800;
}

.role-model__message p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.55;
  font-size: 0.9rem;
}

.role-model__message small {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.4;
}

.role-model__composer {
  margin-top: 10px;
}

.role-model__composer input {
  flex: 1;
}

.role-model__ready-summary {
  position: sticky;
  top: 0;
}

.role-model__ready-summary h3 {
  margin: 4px 0 12px;
  font-size: 1.02rem;
}

.role-model__ready-summary dl {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
}

.role-model__ready-summary div {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fbfbfa;
}

.role-model__ready-summary dt,
.role-model__ready-summary dd {
  margin: 0;
}

.role-model__ready-summary dt {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.role-model__ready-summary dd {
  overflow-wrap: anywhere;
  color: var(--text-soft);
  font-size: 0.86rem;
  font-weight: 800;
  line-height: 1.4;
}

.role-model__ready-summary .role-model__button {
  width: 100%;
  justify-content: center;
}

@media (max-width: 1100px) {
  .role-model__layout {
    grid-template-columns: 1fr;
  }

  .role-model__ready-summary {
    position: static;
  }
}

@media (max-width: 720px) {
  .role-model {
    padding: 14px;
  }

  .role-model__header,
  .role-model__header-actions,
  .role-model__panel-head,
  .role-model__actions,
  .role-model__chat-controls,
  .role-model__composer {
    align-items: stretch;
    flex-direction: column;
  }

  .role-model__mode,
  .role-model__button,
  .role-model__chat-badge {
    justify-content: center;
    width: 100%;
  }

  .role-model__sample-head {
    grid-template-columns: 1fr;
  }

  .role-model__message {
    max-width: 100%;
  }
}
</style>
