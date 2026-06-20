<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '../../stores/useProjectStore'
import { useGraphStore } from '../../stores/useGraphStore'
import {
  deleteNode,
  getNodeCrossReferences,
  getNodeFields,
  saveNodeFields,
  updateNode,
  type CrossReferenceItem,
} from '../../api/projectApi'
import { fileToScaledDataUrl } from '../../utils/imageDataUrl'
import DocFieldsEditor, { type DocFieldRow } from '../../components/workspace/DocFieldsEditor.vue'
import { autoResizeTextarea } from '../../composables/autoResizeField'
import { useCharacterAvatarCache } from '../../composables/useCharacterAvatarCache'

const SAVE_DEBOUNCE_MS = 500

/**
 * 角色卡详情（first_revision 决策 2，对原提案的已批准偏离）。
 *
 * 顶部：名称 + 摘要；中部：添加/编辑/删除“自由字段”（持久化到 node.meta JSON 的 fields 键）；
 * 底部：“关系”区域以标签展示该角色在角色子图中的出边，不绘制连接线。
 */
const props = defineProps<{ charId: string }>()

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const graphStore = useGraphStore()
const { characterGraphId } = storeToRefs(projectStore)

const projectId = computed(() => String(route.params.projectId))
const node = computed(() => graphStore.getNode(props.charId))
const avatarCache = useCharacterAvatarCache()

const fieldRows = ref<DocFieldRow[]>([])
const title = ref('')
const content = ref('')
const avatar = ref('')
const avatarInput = ref<HTMLInputElement | null>(null)
const summaryEl = ref<HTMLTextAreaElement | null>(null)

/** 响应对应的 DOM 或组件事件。 */
function onSummaryInput(event: Event) {
  autoResizeTextarea(event.target as HTMLTextAreaElement)
}

/** 说明 resizeSummary 的局部业务逻辑。 */
function resizeSummary() {
  autoResizeTextarea(summaryEl.value)
}
const saveState = ref('')
const isHydrating = ref(true)
const isDeleting = ref(false)

let saveTimer: ReturnType<typeof setTimeout> | null = null
let isSaving = false
let saveQueued = false
let hydrateGeneration = 0
let pendingFlush: Promise<void> | null = null

// 跨子图反向引用（第 6 阶段）：该角色出现在哪段故事、属于哪个世界观设定等。
const crossRefs = ref<CrossReferenceItem[]>([])
const plotRefs = computed(() => crossRefs.value.filter((r) => r.other_section === 'plot'))
const worldRefs = computed(() => crossRefs.value.filter((r) => r.other_section === 'world'))

/** 加载数据并同步到当前视图状态。 */
async function loadCrossRefs() {
  try {
    const resp = await getNodeCrossReferences(projectId.value, props.charId)
    crossRefs.value = resp.references
  } catch {
    crossRefs.value = []
  }
}

/** 打开目标视图或弹层。 */
function openPlotNode() {
  router.push(`/workspace/${projectId.value}/plot`)
}

/** 打开目标视图或弹层。 */
function openRoleModel() {
  router.push(`/workspace/${projectId.value}/characters/${props.charId}/model`)
}

// 关系：该角色的出边 -> 标签（关系名 + 目标角色名）。
const relations = computed(() =>
  graphStore.outgoingEdges(props.charId).map((edge) => ({
    id: edge.id,
    label: edge.label || edge.relationType || '关联',
    target: graphStore.getNode(edge.target)?.title ?? edge.target,
  })),
)

/** 说明 fieldsFromState 的局部业务逻辑。 */
function fieldsFromState(
  rows: DocFieldRow[],
  avatarValue: string,
): Record<string, string> {
  const fields: Record<string, string> = {}
  if (avatarValue) fields.avatar = avatarValue
  for (const row of rows) {
    const key = row.key.trim()
    if (key) fields[key] = row.value
  }
  return fields
}

/** 说明 fieldsFromRows 的局部业务逻辑。 */
function fieldsFromRows(): Record<string, string> {
  return fieldsFromState(fieldRows.value, avatar.value)
}

/** 保存当前编辑内容到后端或缓存。 */
async function saveFieldsForCharacter(charId: string, fields: Record<string, string>) {
  const saved = await saveNodeFields(projectId.value, charId, fields)
  const savedAvatar = saved.fields.avatar ?? fields.avatar ?? ''
  avatarCache.set(projectId.value, charId, savedAvatar)
  return saved
}

/** 说明 flushSaveForCharacter 的局部业务逻辑。 */
async function flushSaveForCharacter(charId: string) {
  if (!projectId.value || !charId) return

  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }

  const waitStart = Date.now()
  while (isSaving && Date.now() - waitStart < 8000) {
    await new Promise((resolve) => setTimeout(resolve, 30))
  }
  if (isSaving) return

  const snapshotTitle = title.value.trim() || '未命名角色'
  const snapshotContent = content.value
  const snapshotAvatar = avatar.value
  const snapshotRows = fieldRows.value.map((row) => ({ ...row }))
  const nodeSnapshot = graphStore.getNode(charId)
  const titleChanged = snapshotTitle !== (nodeSnapshot?.title ?? '')
  const contentChanged = snapshotContent !== (nodeSnapshot?.content ?? '')

  isSaving = true
  try {
    if (titleChanged || contentChanged) {
      await updateNode(projectId.value, charId, {
        title: snapshotTitle,
        content: snapshotContent,
      })
    }
    await saveFieldsForCharacter(
      charId,
      fieldsFromState(snapshotRows, snapshotAvatar),
    )
    if ((titleChanged || contentChanged) && characterGraphId.value) {
      await graphStore.load(characterGraphId.value, true)
    }
  } finally {
    isSaving = false
    if (saveQueued) {
      saveQueued = false
    }
  }
}

/** 加载数据并同步到当前视图状态。 */
async function loadFields(charId: string, generation: number) {
  const cachedAvatar = avatarCache.get(projectId.value, charId)
  if (cachedAvatar) {
    avatar.value = cachedAvatar
  }

  try {
    const result = await getNodeFields(projectId.value, charId)
    if (generation !== hydrateGeneration) return

    const fetchedAvatar = result.fields.avatar ?? ''
    if (fetchedAvatar) {
      avatar.value = fetchedAvatar
      avatarCache.set(projectId.value, charId, fetchedAvatar)
    } else if (!cachedAvatar) {
      avatar.value = ''
      avatarCache.set(projectId.value, charId, '')
    }

    fieldRows.value = Object.entries(result.fields)
      .filter(([key]) => key !== 'avatar')
      .map(([key, value]) => ({ key, value }))
  } catch {
    if (generation !== hydrateGeneration) return
    if (!avatar.value && cachedAvatar) {
      avatar.value = cachedAvatar
    } else if (!avatar.value) {
      avatar.value = ''
    }
    if (!fieldRows.value.length) {
      fieldRows.value = []
    }
  }
}

/** 打开目标视图或弹层。 */
function openAvatarPicker() {
  avatarInput.value?.click()
}

/** 处理对应的用户交互或组件事件。 */
async function handleAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    saveState.value = '请选择图片文件'
    return
  }
  try {
    const charId = props.charId
    const dataUrl = await fileToScaledDataUrl(file, 640, 0.85)
    avatarCache.set(projectId.value, charId, dataUrl)

    if (charId === props.charId) {
      avatar.value = dataUrl
    }

    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }

    await persistAvatarFor(charId, dataUrl)
  } catch (error) {
    saveState.value = error instanceof Error ? error.message : '图片加载失败'
  }
}

/** 说明 scheduleSave 的局部业务逻辑。 */
function scheduleSave() {
  if (isHydrating.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    void persistAll()
  }, SAVE_DEBOUNCE_MS)
}

/** 持久化当前编辑状态并处理保存队列。 */
async function persistAvatarFor(charId: string, dataUrl: string) {
  if (!projectId.value || !charId) return
  if (isSaving) {
    saveQueued = true
    return
  }

  isSaving = true
  if (charId === props.charId) {
    saveState.value = '保存中…'
  }
  try {
    let fields: Record<string, string> = {}
    try {
      const result = await getNodeFields(projectId.value, charId)
      fields = { ...result.fields }
    } catch {
      fields = {}
    }
    fields.avatar = dataUrl
    await saveFieldsForCharacter(charId, fields)
    if (charId === props.charId) {
      saveState.value = '已保存'
    }
  } catch (error) {
    if (charId === props.charId) {
      saveState.value = error instanceof Error ? `保存失败: ${error.message}` : '保存失败'
    }
  } finally {
    isSaving = false
    if (saveQueued && charId === props.charId) {
      saveQueued = false
      void persistAll()
    } else if (saveQueued) {
      saveQueued = false
    }
  }
}

/** 持久化当前编辑状态并处理保存队列。 */
async function persistAll() {
  const charId = props.charId
  if (!charId) return
  if (isSaving) {
    saveQueued = true
    return
  }

  const nextTitle = title.value.trim() || '未命名角色'
  const nextContent = content.value
  const titleChanged = nextTitle !== (node.value?.title ?? '')
  const contentChanged = nextContent !== (node.value?.content ?? '')

  isSaving = true
  saveState.value = '保存中…'
  try {
    if (titleChanged || contentChanged) {
      await updateNode(projectId.value, charId, {
        title: nextTitle,
        content: nextContent,
      })
    }
    await saveFieldsForCharacter(charId, fieldsFromRows())
    if (titleChanged || contentChanged) {
      if (characterGraphId.value) {
        await graphStore.load(characterGraphId.value, true)
      }
    }
    saveState.value = '已保存'
  } catch (error) {
    saveState.value = error instanceof Error ? `保存失败: ${error.message}` : '保存失败'
  } finally {
    isSaving = false
    if (saveQueued) {
      saveQueued = false
      void persistAll()
    }
  }
}

/** 说明 hydrate 的局部业务逻辑。 */
async function hydrate() {
  const charId = props.charId
  if (!node.value || node.value.id !== charId) return

  const generation = ++hydrateGeneration
  isHydrating.value = true
  title.value = node.value.title
  content.value = node.value.content ?? ''
  await loadFields(charId, generation)
  if (generation === hydrateGeneration) {
    isHydrating.value = false
  }
}

/** 处理对应的用户交互或组件事件。 */
async function handleDelete() {
  const charTitle = title.value.trim() || node.value?.title || '这个角色'
  const confirmed = window.confirm(`删除“${charTitle}”？相关关系边也会一并移除。`)
  if (!confirmed || isDeleting.value) return

  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }

  isDeleting.value = true
  try {
    await deleteNode(projectId.value, props.charId)
    if (characterGraphId.value) {
      await graphStore.load(characterGraphId.value, true)
    }
    router.push(`/workspace/${projectId.value}/characters`)
  } catch (error) {
    saveState.value = error instanceof Error ? `删除失败: ${error.message}` : '删除失败'
  } finally {
    isDeleting.value = false
  }
}

watch(
  characterGraphId,
  async (id) => {
    if (!id) return
    await graphStore.load(id)
    await hydrate()
  },
  { immediate: true },
)

onMounted(() => {
  void loadCrossRefs()
  void hydrate().then(() => resizeSummary())
})

watch(content, () => {
  resizeSummary()
})

watch(
  () => props.charId,
  async (newId, oldId) => {
    if (oldId && oldId !== newId) {
      pendingFlush = flushSaveForCharacter(oldId)
      await pendingFlush
      pendingFlush = null
    }
    void hydrate()
    void loadCrossRefs()
  },
)

watch([title, content, fieldRows], () => {
  scheduleSave()
}, { deep: true })

onBeforeUnmount(async () => {
  const charId = props.charId
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (pendingFlush) {
    await pendingFlush
  }
  await flushSaveForCharacter(charId)
})
</script>

<template>
  <section class="char-detail">
    <header class="char-detail__topbar">
      <button type="button" class="char-detail__back" @click="router.push(`/workspace/${projectId}/characters`)">
        ← 角色
      </button>
      <div class="char-detail__actions">
        <span v-if="saveState" class="char-detail__state">{{ saveState }}</span>
        <button type="button" class="char-detail__model" @click="openRoleModel">
          角色模型
        </button>
      </div>
    </header>

    <input
      ref="avatarInput"
      class="char-detail__file-input"
      type="file"
      accept="image/*"
      @change="handleAvatarChange"
    />

    <header class="char-detail__head">
      <div
        class="char-detail__avatar"
        role="button"
        tabindex="0"
        :aria-label="avatar ? '点击更换头像' : '点击上传头像'"
        title="点击更换头像"
        @click.stop="openAvatarPicker"
        @keydown.enter="openAvatarPicker"
      >
        <img v-if="avatar" :src="avatar" :alt="title || '角色头像'" />
        <span v-else class="char-detail__avatar-placeholder">+</span>
      </div>
      <div class="char-detail__intro">
        <input
          v-model="title"
          class="char-detail__title"
          type="text"
          placeholder="角色名称"
          spellcheck="false"
        />
        <textarea
          ref="summaryEl"
          v-model="content"
          class="char-detail__summary"
          rows="1"
          placeholder="添加摘要…"
          spellcheck="true"
          @input="onSummaryInput"
        />
      </div>
    </header>

    <DocFieldsEditor v-model="fieldRows" />

    <div class="char-detail__section">
      <h3>角色关系</h3>
      <p v-if="relations.length === 0" class="char-detail__hint">暂无角色关系。</p>
      <div v-else class="char-detail__relations">
        <span v-for="rel in relations" :key="rel.id" class="char-detail__rel">
          {{ rel.label }} → {{ rel.target }}
        </span>
      </div>
    </div>

    <div class="char-detail__section">
      <h3>跨子图引用</h3>
      <p v-if="crossRefs.length === 0" class="char-detail__hint">暂无跨引用。</p>
      <template v-else>
        <div v-if="worldRefs.length" class="char-detail__xref-group">
          <span class="char-detail__xref-label">所属世界观：</span>
          <span v-for="ref in worldRefs" :key="ref.edge_id" class="char-detail__rel">
            {{ ref.other_title }}
          </span>
        </div>
        <div v-if="plotRefs.length" class="char-detail__xref-group">
          <span class="char-detail__xref-label">出现于剧情：</span>
          <button
            v-for="ref in plotRefs"
            :key="ref.edge_id"
            type="button"
            class="char-detail__rel char-detail__rel--link"
            @click="openPlotNode"
          >
            {{ ref.other_title }}
          </button>
        </div>
      </template>
    </div>

    <footer class="char-detail__footer">
      <button
        type="button"
        class="char-detail__delete"
        :disabled="isDeleting"
        @click="handleDelete"
      >
        {{ isDeleting ? '删除中…' : '删除角色' }}
      </button>
    </footer>
  </section>
</template>

<style scoped>
.char-detail {
  max-width: 640px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.char-detail__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.char-detail__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.char-detail__back {
  font-size: 13px;
  color: var(--muted, #888);
  background: none;
  border: none;
  cursor: pointer;
}
.char-detail__model {
  padding: 7px 12px;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.char-detail__file-input {
  display: none;
}
.char-detail__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.char-detail__avatar {
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  padding: 0;
  border: 1px dashed var(--border, #ddd);
  border-radius: 999px;
  overflow: hidden;
  background: var(--panel-strong, #fafafa);
  cursor: pointer;
}
.char-detail__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.char-detail__avatar-placeholder {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  font-size: 28px;
  color: var(--muted, #888);
}
.char-detail__intro {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.char-detail__title {
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  cursor: text;
}
.char-detail__title:focus {
  outline: none;
}
.char-detail__summary {
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  resize: none;
  overflow: hidden;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-soft, #666);
  cursor: text;
  min-height: 1.6em;
}
.char-detail__summary:focus {
  outline: none;
  color: var(--text);
}
.char-detail__summary::placeholder,
.char-detail__title::placeholder {
  color: var(--muted, #aaa);
}
.char-detail__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.char-detail__hint {
  color: var(--muted, #888);
  font-size: 13px;
}
.char-detail__state {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--muted, #888);
}
.char-detail__relations {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.char-detail__rel {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-deep);
}
.char-detail__rel--link {
  border: none;
  cursor: pointer;
}
.char-detail__xref-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.char-detail__xref-label {
  font-size: 13px;
  color: var(--muted, #666);
}
.char-detail__footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--border, #e5e7eb);
}
.char-detail__delete {
  padding: 8px 14px;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  background: #fff;
  color: #dc2626;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.char-detail__delete:hover:not(:disabled) {
  background: #fef2f2;
}
.char-detail__delete:disabled {
  opacity: 0.6;
  cursor: wait;
}
</style>
