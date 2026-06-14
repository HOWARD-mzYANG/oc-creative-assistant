<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useCenterStageStore } from '../../stores/useCenterStageStore'
import { getNodeFields, saveNodeFields, updateNode } from '../../api/projectApi'
import PlotCastRow from './PlotCastRow.vue'

/**
 * Node detail — a stationery writing surface (second_revision change A, W3).
 *
 * Reads the initial snapshot from useCenterStageStore.detailNode, lets the writer
 * edit title / body / tags / status + free-form attributes, with debounced auto-save.
 * "Back to canvas" returns (SubgraphCanvas reloads on mode change).
 */
const props = defineProps<{ nodeId: string }>()
const emit = defineEmits<{ return: [] }>()

const route = useRoute()
const centerStage = useCenterStageStore()
const { detailNode } = storeToRefs(centerStage)

const projectId = String(route.params.projectId)
const SAVE_DEBOUNCE_MS = 500

let saveTimer: ReturnType<typeof setTimeout> | null = null
let isSaving = false
let saveQueued = false
const isHydrating = ref(true)

const TYPE_LABEL: Record<string, string> = {
  character: '角色',
  worldbuilding: '世界观',
  world: '世界观',
  plot: '情节',
  idea: '想法',
  research: '资料',
  structure: '结构',
}

const title = ref('')
const body = ref('')
const tagsText = ref('')
const status = ref('draft')
const saveState = ref('')

interface FieldRow {
  key: string
  value: string
}
const fieldRows = ref<FieldRow[]>([])

const typeLabel = computed(() => TYPE_LABEL[detailNode.value?.nodeType ?? ''] ?? '笔记')
const isPlot = computed(() => detailNode.value?.nodeType === 'plot')

function loadFromSnapshot() {
  const node = detailNode.value
  title.value = node?.title ?? ''
  body.value = node?.content ?? ''
  tagsText.value = (node?.tags ?? []).join(', ')
  status.value = node?.status ?? 'draft'
}

async function hydrate() {
  isHydrating.value = true
  loadFromSnapshot()
  await loadFields()
  isHydrating.value = false
}

async function loadFields() {
  try {
    const result = await getNodeFields(projectId, props.nodeId)
    fieldRows.value = Object.entries(result.fields).map(([key, value]) => ({ key, value }))
  } catch {
    fieldRows.value = []
  }
}

function addField() {
  fieldRows.value.push({ key: '', value: '' })
}
function removeField(index: number) {
  fieldRows.value.splice(index, 1)
}

function scheduleSave() {
  if (isHydrating.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    void persist()
  }, SAVE_DEBOUNCE_MS)
}

async function persist() {
  if (isSaving) {
    saveQueued = true
    return
  }

  const tags = tagsText.value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  const fields: Record<string, string> = {}
  for (const row of fieldRows.value) {
    const key = row.key.trim()
    if (key) fields[key] = row.value
  }

  isSaving = true
  saveState.value = '保存中…'
  try {
    await updateNode(projectId, props.nodeId, {
      title: title.value,
      content: body.value,
      tags,
      status: status.value,
    })
    await saveNodeFields(projectId, props.nodeId, fields)
    saveState.value = '已保存'
  } catch (e) {
    saveState.value = e instanceof Error ? `保存失败: ${e.message}` : '保存失败'
  } finally {
    isSaving = false
    if (saveQueued) {
      saveQueued = false
      void persist()
    }
  }
}

onMounted(() => {
  void hydrate()
})
watch(
  () => props.nodeId,
  () => {
    void hydrate()
  },
)

watch([title, body, tagsText, status, fieldRows], () => {
  scheduleSave()
}, { deep: true })

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<template>
  <section class="detail" :class="{ 'detail--plot': isPlot }">
    <div class="detail__bar">
      <button type="button" class="detail__back" @click="emit('return')">← 返回画布</button>
      <span class="detail__state">{{ saveState }}</span>
    </div>

    <div class="detail__scroll" :class="{ 'detail__scroll--plot': isPlot }">
      <div class="detail__content" :class="{ 'detail__content--plot': isPlot }">
        <article class="sheet" :class="{ 'sheet--plot': isPlot }">
          <div class="sheet__stack">
            <p class="eyebrow sheet__eyebrow">{{ typeLabel }}</p>

            <input
              v-model="title"
              class="sheet__title"
              type="text"
              placeholder="未命名"
              spellcheck="false"
            />

            <textarea
              v-model="body"
              class="sheet__body"
              :rows="isPlot ? 6 : 10"
              placeholder="开始书写：描述这个角色、地点或瞬间…"
            ></textarea>

            <div v-if="!isPlot" class="sheet__meta">
              <label class="sheet__meta-row">
                <span class="eyebrow">标签</span>
                <input v-model="tagsText" type="text" placeholder="主角，第一幕" />
              </label>
              <label class="sheet__meta-row sheet__meta-row--status">
                <span class="eyebrow">状态</span>
                <select v-model="status">
                  <option value="draft">草稿</option>
                  <option value="synced">已同步</option>
                  <option value="outdated">需更新</option>
                </select>
              </label>
            </div>

            <div class="sheet__fields">
              <div class="sheet__fields-head">
                <span class="eyebrow">属性</span>
                <button type="button" class="sheet__add" @click="addField">+ 添加字段</button>
              </div>
              <p v-if="fieldRows.length === 0" class="sheet__hint">暂无属性。</p>
              <div v-for="(row, index) in fieldRows" :key="index" class="sheet__field">
                <input v-model="row.key" class="sheet__field-key" placeholder="阵营" />
                <span class="sheet__field-sep">·</span>
                <input v-model="row.value" class="sheet__field-val" placeholder="焰火王国" />
                <button type="button" class="sheet__field-del" @click="removeField(index)">✕</button>
              </div>
            </div>
          </div>

          <PlotCastRow
            v-if="isPlot"
            class="sheet__cast"
            :project-id="projectId"
            :plot-node-id="nodeId"
          />
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.detail {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--app-bg);
}

.detail--plot {
  overflow: hidden;
}

.detail__bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.detail__back {
  border: none;
  background: none;
  color: var(--text-soft);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.detail__back:hover {
  color: var(--accent);
}

.detail__state {
  font-size: 12px;
  color: var(--muted);
}

.detail__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 24px 60px;
  display: flex;
  justify-content: center;
}

.detail__scroll--plot {
  padding: 14px 24px 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.detail__content {
  width: 100%;
  max-width: 660px;
  display: flex;
  flex-direction: column;
}

.detail__content--plot {
  flex: 1;
  min-height: 0;
  width: 100%;
}

/* —— the sheet of paper —— */
.sheet {
  width: 100%;
  padding: 44px 52px 40px;
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 4px;
  box-shadow: var(--shadow-lg);
  background-image:
    linear-gradient(var(--paper), var(--paper)),
    repeating-linear-gradient(
      to bottom,
      transparent 0,
      transparent 33px,
      rgba(28, 25, 23, 0.04) 33px,
      rgba(28, 25, 23, 0.04) 34px
    );
  background-clip: padding-box;
  position: relative;
}

.sheet--plot {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  overflow: hidden;
  padding-bottom: 0;
  border-radius: 4px 4px 0 0;
  border-bottom: none;
}

.sheet__stack {
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding-bottom: 8px;
}

.sheet--plot .sheet__body {
  flex: 1 1 auto;
  min-height: 5em;
  resize: none;
}

.sheet__cast {
  flex-shrink: 0;
  padding-bottom: 24px;
  overflow: visible;
}

.sheet::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 34px;
  width: 1px;
  background: rgba(233, 130, 74, 0.25);
}

.sheet__eyebrow {
  margin: 0 0 10px;
}

.sheet__title {
  width: 100%;
  border: none;
  background: transparent;
  font-family: var(--font-serif);
  font-size: 2.1rem;
  font-weight: 500;
  letter-spacing: -0.015em;
  color: var(--text);
  padding: 0;
}

.sheet__title::placeholder {
  color: rgba(28, 25, 23, 0.25);
}

.sheet__title:focus {
  outline: none;
}

.sheet__body {
  width: 100%;
  margin-top: 14px;
  border: none;
  background: transparent;
  resize: vertical;
  font-family: var(--font-serif);
  font-size: 1.04rem;
  line-height: 34px;
  color: var(--text-soft);
}

.sheet__body:focus {
  outline: none;
}

.sheet__body::placeholder {
  color: rgba(28, 25, 23, 0.28);
}

.sheet__meta {
  display: flex;
  gap: 28px;
  margin-top: 28px;
  padding-top: 18px;
  border-top: 1px solid rgba(28, 25, 23, 0.08);
}

.sheet__meta-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.sheet__meta-row--status {
  flex: 0 0 140px;
}

.sheet__meta-row input,
.sheet__meta-row select {
  border: none;
  border-bottom: 1px solid var(--border-strong);
  background: transparent;
  padding: 4px 0;
  font-size: 0.92rem;
  color: var(--text);
}

.sheet__meta-row input:focus,
.sheet__meta-row select:focus {
  outline: none;
  border-bottom-color: var(--accent);
}

.sheet__fields {
  margin-top: 24px;
}

.sheet__fields-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.sheet__add {
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.sheet__hint {
  color: var(--muted);
  font-size: 13px;
}

.sheet__field {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
}

.sheet__field-key {
  width: 150px;
  border: none;
  background: transparent;
  font-weight: 600;
  color: var(--text);
}

.sheet__field-sep {
  color: var(--muted);
}

.sheet__field-val {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-soft);
}

.sheet__field-key:focus,
.sheet__field-val:focus {
  outline: none;
}

.sheet__field-del {
  border: none;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.15s;
}

.sheet__field:hover .sheet__field-del {
  opacity: 1;
}
</style>
