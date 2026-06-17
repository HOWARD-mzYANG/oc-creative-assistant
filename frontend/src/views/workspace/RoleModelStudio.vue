<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getRoleChatHistory,
  getRoleModelJob,
  getRoleModelOverview,
  startRoleModelTraining,
  streamRoleChat,
  type RoleChatMessageDto,
  type RoleModelJobDto,
  type RoleModelOverviewDto,
} from '../../api/roleModelApi'

const props = defineProps<{ charId: string }>()

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId))

const overview = ref<RoleModelOverviewDto | null>(null)
const job = ref<RoleModelJobDto | null>(null)
const selectedJobId = ref('')
const isLoading = ref(false)
const isTraining = ref(false)
const isHistoryLoading = ref(false)
const error = ref('')
const draft = ref('')
const chatMessages = ref<RoleChatMessageDto[]>([])
const streamingReply = ref('')
const isChatting = ref(false)
const isJobMenuOpen = ref(false)
const jobSelectEl = ref<HTMLElement | null>(null)

let pollTimer: ReturnType<typeof window.setInterval> | null = null

const snapshot = computed(() => overview.value?.snapshot ?? null)
const materialBrief = computed(() => overview.value?.material_brief ?? null)
const jobs = computed(() => {
  const seen = new Set<string>()
  const items: RoleModelJobDto[] = []
  for (const item of [job.value, ...(overview.value?.jobs ?? [])]) {
    if (!item || seen.has(item.id)) continue
    seen.add(item.id)
    items.push(item)
  }
  return items
})
const selectedJob = computed(() => jobs.value.find((item) => item.id === selectedJobId.value) ?? null)
const activeJob = computed(() => selectedJob.value ?? job.value ?? overview.value?.latest_job ?? null)
const canTrain = computed(() => Boolean(overview.value?.service_online) && !isTraining.value)
const canUseAdapter = computed(() => activeJob.value?.status === 'succeeded')
const serviceLabel = computed(() => {
  if (!overview.value) return '加载中'
  if (!overview.value.service_configured) return '未配置'
  if (!overview.value.service_online) return '离线'
  return '在线'
})
const jobLabel = computed(() => {
  const status = activeJob.value?.status
  if (!status) return '暂无任务'
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '训练中',
    succeeded: '已完成',
    failed: '失败',
  }
  return labels[status] ?? status
})
const selectedJobLabel = computed(() => {
  if (!jobs.value.length) return '暂无可选模型'
  return activeJob.value ? labelForJob(activeJob.value) : '选择模型'
})

function labelForJob(item: RoleModelJobDto) {
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '训练中',
    succeeded: '已完成',
    failed: '失败',
  }
  const time = new Date(item.created_at).toLocaleString()
  return `${labels[item.status] ?? item.status} · ${item.sample_count || '准备中'} 条 · ${time}`
}

function toggleJobMenu() {
  if (!jobs.value.length) return
  isJobMenuOpen.value = !isJobMenuOpen.value
}

function selectJob(jobId: string) {
  selectedJobId.value = jobId
  isJobMenuOpen.value = false
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node)) return
  if (!jobSelectEl.value?.contains(target)) {
    isJobMenuOpen.value = false
  }
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

function shouldPoll(current: RoleModelJobDto | null) {
  return current?.status === 'queued' || current?.status === 'running'
}

function startPolling() {
  stopPolling()
  if (!activeJob.value || !shouldPoll(activeJob.value)) return
  pollTimer = window.setInterval(() => {
    void refreshJob()
  }, 2000)
}

async function loadOverview() {
  isLoading.value = true
  error.value = ''
  try {
    const data = await getRoleModelOverview(projectId.value, props.charId)
    overview.value = data
    job.value = data.latest_job ?? null
    const currentStillExists = selectedJobId.value && data.jobs.some((item) => item.id === selectedJobId.value)
    if (!currentStillExists) {
      selectedJobId.value =
        data.latest_job?.id ??
        data.jobs.find((item) => item.status === 'succeeded')?.id ??
        data.jobs[0]?.id ??
        ''
    }
    await loadSelectedHistory()
    startPolling()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '角色模型信息加载失败'
  } finally {
    isLoading.value = false
  }
}

async function refreshJob() {
  const current = activeJob.value
  if (!current) return
  try {
    job.value = await getRoleModelJob(projectId.value, props.charId, current.id)
    if (!shouldPoll(job.value)) {
      stopPolling()
      await loadOverview()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '训练任务刷新失败'
    stopPolling()
  }
}

async function handleTrain() {
  if (!canTrain.value) return
  isTraining.value = true
  error.value = ''
  try {
    job.value = await startRoleModelTraining(projectId.value, props.charId)
    selectedJobId.value = job.value.id
    chatMessages.value = []
    startPolling()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '训练任务启动失败'
  } finally {
    isTraining.value = false
  }
}

async function loadSelectedHistory() {
  const current = selectedJob.value
  if (!current || current.status !== 'succeeded' || !overview.value?.service_online) {
    chatMessages.value = []
    return
  }
  isHistoryLoading.value = true
  try {
    const history = await getRoleChatHistory(projectId.value, props.charId, current.id)
    chatMessages.value = history
      .filter((item) => item.role === 'user' || item.role === 'assistant')
      .map((item) => ({ role: item.role, content: item.content }))
  } catch {
    chatMessages.value = []
  } finally {
    isHistoryLoading.value = false
  }
}

async function handleSend() {
  const text = draft.value.trim()
  if (!text || isChatting.value) return
  draft.value = ''
  chatMessages.value.push({ role: 'user', content: text })
  streamingReply.value = ''
  isChatting.value = true
  error.value = ''

  try {
    await streamRoleChat(
      projectId.value,
      props.charId,
      {
        message: text,
        job_id: canUseAdapter.value ? activeJob.value?.id : null,
        history: chatMessages.value.slice(0, -1),
      },
      (event) => {
        if (event.type === 'token') {
          streamingReply.value += event.text
        } else if (event.type === 'error') {
          error.value = event.message
        }
      },
    )
    if (streamingReply.value.trim()) {
      chatMessages.value.push({ role: 'assistant', content: streamingReply.value })
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '角色对话失败'
  } finally {
    streamingReply.value = ''
    isChatting.value = false
  }
}

function backToCharacter() {
  router.push(`/workspace/${projectId.value}/characters/${props.charId}`)
}

watch(
  () => props.charId,
  () => {
    selectedJobId.value = ''
    chatMessages.value = []
    void loadOverview()
  },
)

watch(selectedJobId, () => {
  streamingReply.value = ''
  void loadSelectedHistory()
  startPolling()
})

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  void loadOverview()
})

onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})
</script>

<template>
  <section class="role-model">
    <header class="role-model__topbar">
      <button type="button" class="role-model__back" @click="backToCharacter">← 角色卡</button>
      <div class="role-model__title">
        <span>角色模型</span>
        <strong>{{ snapshot?.character_name || '加载中' }}</strong>
      </div>
      <span class="role-model__service" :class="{ 'is-online': overview?.service_online }">
        {{ serviceLabel }}
      </span>
    </header>

    <p v-if="error" class="role-model__error">{{ error }}</p>

    <main class="role-model__grid">
      <section class="role-model__panel">
        <header class="role-model__panel-head">
          <h2>资料快照</h2>
          <button type="button" class="role-model__ghost" :disabled="isLoading" @click="loadOverview">
            刷新
          </button>
        </header>
        <p class="role-model__summary">{{ snapshot?.character_summary || '暂无摘要' }}</p>
        <div class="role-model__facts">
          <span v-for="(value, key) in snapshot?.fields" :key="key">
            {{ key }}：{{ value }}
          </span>
        </div>
        <div class="role-model__metric-row">
          <span>关系 {{ snapshot?.relations.length ?? 0 }}</span>
          <span>跨引用 {{ snapshot?.cross_references.length ?? 0 }}</span>
          <span>相关节点 {{ snapshot?.related_nodes.length ?? 0 }}</span>
        </div>
        <div v-if="materialBrief" class="role-model__brief">
          <strong>资料整理稿</strong>
          <span>{{ materialBrief.identity }}</span>
          <span v-if="materialBrief.voice_style">语气：{{ materialBrief.voice_style }}</span>
          <span v-if="materialBrief.known_facts.length">
            事实：{{ materialBrief.known_facts.slice(0, 3).join('；') }}
          </span>
        </div>
        <p v-if="overview && !overview.service_online" class="role-model__hint">
          训练服务不可用时仍可用 API + 当前角色资料进行兜底对话。
        </p>
      </section>

      <section class="role-model__panel">
        <header class="role-model__panel-head">
          <h2>LoRA 训练</h2>
          <button type="button" class="role-model__primary" :disabled="!canTrain" @click="handleTrain">
            {{ isTraining ? '启动中' : '重新整理并训练' }}
          </button>
        </header>
        <label class="role-model__select">
          <span>已有模型</span>
          <div
            ref="jobSelectEl"
            class="role-model__custom-select"
            :class="{ 'is-disabled': !jobs.length }"
            @keydown.escape.stop="isJobMenuOpen = false"
          >
            <button
              type="button"
              class="role-model__select-trigger"
              :class="{ 'is-open': isJobMenuOpen }"
              :disabled="!jobs.length"
              aria-haspopup="listbox"
              :aria-expanded="isJobMenuOpen"
              @click="toggleJobMenu"
            >
              <span class="role-model__select-value">{{ selectedJobLabel }}</span>
              <span class="role-model__select-arrow" aria-hidden="true"></span>
            </button>

            <ul v-if="isJobMenuOpen" class="role-model__select-options" role="listbox">
              <li
                v-for="item in jobs"
                :key="item.id"
                role="option"
                :aria-selected="item.id === selectedJobId"
              >
                <button
                  type="button"
                  class="role-model__select-option"
                  :class="{ 'is-selected': item.id === selectedJobId }"
                  @click="selectJob(item.id)"
                >
                  <span>{{ labelForJob(item) }}</span>
                  <span v-if="item.id === selectedJobId" class="role-model__select-check">已选</span>
                </button>
              </li>
            </ul>
          </div>
        </label>
        <div class="role-model__job">
          <span class="role-model__job-status">{{ jobLabel }}</span>
          <span v-if="activeJob">样本 {{ activeJob.sample_count || '准备中' }}</span>
        </div>
        <pre v-if="activeJob?.log_tail" class="role-model__log">{{ activeJob.log_tail }}</pre>
        <p v-else class="role-model__hint">
          任务会生成 Alpaca SFT 数据、dataset_info.json 和 LLaMA-Factory train.yaml。
        </p>
      </section>

      <section class="role-model__panel role-model__panel--chat">
        <header class="role-model__panel-head">
          <h2>角色对话</h2>
          <span class="role-model__mode">{{ canUseAdapter ? '微调模型' : '资料' }}</span>
        </header>
        <div class="role-model__chat">
          <p v-if="isHistoryLoading" class="role-model__hint">正在读取远程聊天记录...</p>
          <p v-if="!chatMessages.length && !streamingReply" class="role-model__hint">
            请选择已完成的角色 LoRA 对话；没有可用模型时会用现有 API + 快照资料。
          </p>
          <article
            v-for="(message, index) in chatMessages"
            :key="`${message.role}-${index}`"
            class="role-chat-msg"
            :class="`role-chat-msg--${message.role}`"
          >
            {{ message.content }}
          </article>
          <article v-if="streamingReply" class="role-chat-msg role-chat-msg--assistant">
            {{ streamingReply }}
          </article>
        </div>
        <form class="role-model__composer" @submit.prevent="handleSend">
          <input
            v-model="draft"
            type="text"
            placeholder="和这个角色说句话"
            :disabled="isChatting"
          />
          <button type="submit" :disabled="!draft.trim() || isChatting">
            {{ isChatting ? '生成中' : '发送' }}
          </button>
        </form>
      </section>
    </main>
  </section>
</template>

<style scoped>
.role-model {
  min-height: 100%;
  padding: 24px;
  background: var(--canvas-bg);
  color: var(--text);
}

.role-model__topbar,
.role-model__panel-head,
.role-model__composer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.role-model__topbar {
  margin-bottom: 20px;
}

.role-model__back,
.role-model__ghost,
.role-model__primary,
.role-model__composer button {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  background: var(--panel);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}

.role-model__primary,
.role-model__composer button {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
  font-weight: 700;
}

.role-model__primary:disabled,
.role-model__composer button:disabled,
.role-model__ghost:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.role-model__title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.role-model__title span {
  font-size: 12px;
  color: var(--muted);
}

.role-model__title strong {
  font-size: 20px;
}

.role-model__service,
.role-model__mode,
.role-model__job-status {
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(127, 127, 127, 0.12);
  color: var(--text-soft);
  font-size: 12px;
  font-weight: 700;
}

.role-model__service.is-online {
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
}

.role-model__grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}

.role-model__panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  padding: 18px;
  box-shadow: var(--shadow-sm);
}

.role-model__panel--chat {
  grid-column: 1 / -1;
}

.role-model__panel-head {
  justify-content: space-between;
  margin-bottom: 14px;
}

.role-model__panel-head h2 {
  margin: 0;
  font-size: 16px;
}

.role-model__summary,
.role-model__hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-soft);
}

.role-model__facts,
.role-model__metric-row,
.role-model__job,
.role-model__brief {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.role-model__facts {
  margin-top: 14px;
}

.role-model__facts span,
.role-model__metric-row span,
.role-model__job span {
  border-radius: 7px;
  padding: 5px 9px;
  background: rgba(127, 127, 127, 0.08);
  font-size: 12px;
  color: var(--text-soft);
}

.role-model__metric-row {
  margin-top: 14px;
}

.role-model__job {
  flex-direction: column;
  align-items: flex-start;
}

.role-model__brief {
  margin-top: 14px;
  flex-direction: column;
  align-items: flex-start;
}

.role-model__brief strong {
  font-size: 12px;
}

.role-model__brief span {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-soft);
}

.role-model__select {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--text-soft);
}

.role-model__custom-select {
  position: relative;
  width: 100%;
}

.role-model__select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
  min-height: 46px;
  border: 1px solid var(--border);
  border-radius: var(--radius, 12px);
  padding: 10px 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 250, 249, 0.98)),
    var(--panel);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}

.role-model__select-trigger:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  box-shadow: var(--shadow-md);
}

.role-model__select-trigger:focus,
.role-model__select-trigger.is-open {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft), var(--shadow-sm);
}

.role-model__select-trigger:disabled {
  color: var(--muted);
  cursor: not-allowed;
  opacity: 0.72;
  box-shadow: none;
}

.role-model__select-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-model__select-arrow {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  transform: translateY(-2px) rotate(45deg);
  transition: transform 0.16s ease;
}

.role-model__select-trigger.is-open .role-model__select-arrow {
  transform: translateY(2px) rotate(225deg);
}

.role-model__custom-select.is-disabled .role-model__select-arrow {
  opacity: 0.5;
}

.role-model__select-options {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 30;
  max-height: 248px;
  margin: 0;
  padding: 7px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius, 12px);
  background: var(--panel);
  box-shadow: var(--shadow-lg);
  animation: roleModelMenuIn 0.15s ease-out both;
}

.role-model__select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 38px;
  border: 0;
  border-radius: var(--radius-sm, 8px);
  padding: 8px 10px;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.role-model__select-option span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-model__select-option:hover,
.role-model__select-option:focus {
  outline: none;
  background: var(--accent-soft);
}

.role-model__select-option.is-selected {
  color: var(--accent-deep);
  font-weight: 700;
}

.role-model__select-check {
  flex: 0 0 auto;
  color: var(--accent);
  font-size: 12px;
}

@keyframes roleModelMenuIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.role-model__log {
  height: 260px;
  max-width: 100%;
  box-sizing: border-box;
  overflow: auto;
  margin: 14px 0 0;
  padding: 12px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.05);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.role-model__chat {
  height: 360px;
  max-width: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(127, 127, 127, 0.06);
}

.role-chat-msg {
  max-width: 76%;
  box-sizing: border-box;
  padding: 9px 12px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.role-chat-msg--user {
  align-self: flex-end;
  background: var(--accent);
  color: #fff;
}

.role-chat-msg--assistant {
  align-self: flex-start;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
}

.role-model__composer {
  margin-top: 12px;
}

.role-model__composer input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 11px;
  font: inherit;
}

.role-model__error {
  margin: 0 0 12px;
  color: #dc2626;
  font-size: 13px;
}

@media (max-width: 860px) {
  .role-model__grid {
    grid-template-columns: 1fr;
  }
}
</style>
