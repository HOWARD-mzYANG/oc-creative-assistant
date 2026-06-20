<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { loadSubgraph, saveSubgraph } from '../../api/graphApi'
import { getNodeFields } from '../../api/projectApi'
import { useProjectStore } from '../../stores/useProjectStore'
import { useGraphStore } from '../../stores/useGraphStore'
import { graphDtoToSnapshot, snapshotToSaveDto } from '../../utils/graphTransform'
import { createCreativeNode } from '../../utils/nodeFactory'
import { useCharacterAvatarCache } from '../../composables/useCharacterAvatarCache'

/**
 * 角色列表（first_revision 决策 2，对原提案的已批准偏离）。
 *
 * 使用来自角色子图节点的 Notion 风格卡片网格；角色关系不画成 Vue Flow 连线，
 * 而是在详情页以标签展示。点击卡片会打开 CharacterCardDetail。
 */
const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const graphStore = useGraphStore()
const { characterGraphId } = storeToRefs(projectStore)
const { nodes, isLoading, error } = storeToRefs(graphStore)

const avatarByCharacterId = ref<Record<string, string>>({})
const avatarCache = useCharacterAvatarCache()
const createOpen = ref(false)
const createName = ref('')
const createSummary = ref('')
const isCreating = ref(false)
const createError = ref('')

const projectId = computed(() => String(route.params.projectId))
const characterCount = computed(() => nodes.value.length)

watch(
  characterGraphId,
  (id) => {
    if (id) void graphStore.load(id)
  },
  { immediate: true },
)

/** 读取指定资源并返回前端可用数据。 */
async function readAvatar(nodeId: string): Promise<string> {
  try {
    const result = await getNodeFields(projectId.value, nodeId)
    return result.fields.avatar ?? ''
  } catch {
    return ''
  }
}

/** 说明 avatarFor 的局部业务逻辑。 */
function avatarFor(nodeId: string): string {
  return avatarByCharacterId.value[nodeId] || avatarCache.get(projectId.value, nodeId)
}

/** 加载数据并同步到当前视图状态。 */
async function loadAvatars(nodeIds: string[]) {
  if (!nodeIds.length) {
    avatarByCharacterId.value = avatarCache.snapshot(projectId.value)
    return
  }

  const next = {
    ...avatarCache.snapshot(projectId.value),
    ...avatarByCharacterId.value,
  }

  const pairs = await Promise.all(
    nodeIds.map(async (id) => [id, await readAvatar(id)] as const),
  )

  for (const [id, avatar] of pairs) {
    const cached = avatarCache.get(projectId.value, id)
    if (avatar) {
      next[id] = avatar
      avatarCache.set(projectId.value, id, avatar)
    } else if (cached) {
      next[id] = cached
    } else if (!(id in next)) {
      next[id] = ''
    }
  }

  avatarByCharacterId.value = next
}

watch(
  [nodes, () => route.fullPath],
  ([list]) => {
    void loadAvatars(list.map((node) => node.id))
  },
  { immediate: true },
)

/** 打开目标视图或弹层。 */
function openCharacter(charId: string) {
  router.push(`/workspace/${projectId.value}/characters/${charId}`)
}

/** 说明 characterInitials 的局部业务逻辑。 */
function characterInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] ?? ''}${parts[1][0] ?? ''}`.toUpperCase()
}

/** 节点类型标签已经在底部展示，正文区域只显示额外标签。 */
function extraTags(tags: string[] | undefined): string[] {
  return (tags ?? []).filter((tag) => tag.toLowerCase() !== 'character')
}

/** 打开目标视图或弹层。 */
function openCreate() {
  createName.value = ''
  createSummary.value = ''
  createError.value = ''
  createOpen.value = true
}

/** 关闭目标视图或弹层。 */
function closeCreate() {
  if (isCreating.value) return
  createOpen.value = false
}

/** 处理对应的用户交互或组件事件。 */
async function handleCreate() {
  const graphId = characterGraphId.value
  const name = createName.value.trim()
  if (!graphId || !name || isCreating.value) return

  isCreating.value = true
  createError.value = ''
  try {
    const graph = await loadSubgraph(graphId)
    const snapshot = graphDtoToSnapshot(graph)
    const index = snapshot.nodes.length + 1
    const newNode = createCreativeNode('character', index, {
      x: 40 + (index % 4) * 220,
      y: 40 + Math.floor(index / 4) * 160,
    })
    newNode.data.title = name
    newNode.data.content = createSummary.value.trim()

    snapshot.nodes.push(newNode)
    await saveSubgraph(graphId, snapshotToSaveDto(snapshot))
    await graphStore.load(graphId, true)
    createOpen.value = false
    router.push(`/workspace/${projectId.value}/characters/${newNode.id}`)
  } catch (e) {
    createError.value = e instanceof Error ? e.message : '创建角色失败'
  } finally {
    isCreating.value = false
  }
}
</script>

<template>
  <section class="card-list">
    <header class="card-list__header">
      <div class="card-list__intro">
        <h2>角色</h2>
        <p class="card-list__hint">
          建立你的角色阵容：打开卡片即可编辑字段并上传头像。
        </p>
      </div>
      <span v-if="!isLoading && !error" class="card-list__count">{{ characterCount }}</span>
    </header>

    <p v-if="error" class="card-list__error">{{ error }}</p>
    <p v-else-if="isLoading" class="card-list__hint card-list__hint--block">加载中…</p>

    <div v-else class="card-list__grid">
      <article
        v-for="(node, index) in nodes"
        :key="node.id"
        class="id-card"
        @click="openCharacter(node.id)"
      >
        <header class="id-card__band">
          <span class="id-card__code">CHR-{{ String(index + 1).padStart(3, '0') }}</span>
          <span class="id-card__chip" aria-hidden="true"></span>
        </header>

        <div class="id-card__main">
          <div class="id-card__photo" aria-hidden="true">
            <img
              v-if="avatarFor(node.id)"
              :src="avatarFor(node.id)"
              :alt="`${node.title} 头像`"
            />
            <span v-else class="id-card__initials">{{ characterInitials(node.title) }}</span>
          </div>
          <div class="id-card__id">
            <span class="id-card__label">姓名</span>
            <h3 class="id-card__name">{{ node.title }}</h3>
            <p
              class="id-card__summary"
              :class="{ 'id-card__summary--empty': !node.content }"
            >{{ node.content || '暂无摘要' }}</p>
            <div v-if="extraTags(node.tags).length" class="id-card__tags">
              <span v-for="tag in extraTags(node.tags)" :key="tag" class="id-card__tag">{{ tag }}</span>
            </div>
          </div>
        </div>

        <footer class="id-card__footer">
          <span class="id-card__role">角色</span>
        </footer>
      </article>

      <button type="button" class="id-card id-card--create" @click="openCreate">
        <span class="id-card__create-photo" aria-hidden="true">+</span>
        <span class="id-card__create-label">新建角色</span>
        <span class="id-card__create-sub">加入角色阵容</span>
      </button>
    </div>

    <div v-if="createOpen" class="card-list__modal" @click.self="closeCreate">
      <form class="create-card" @submit.prevent="handleCreate">
        <h3 class="create-card__title">新建角色</h3>
        <label class="create-card__field">
          <span>名称</span>
          <input v-model="createName" type="text" placeholder="角色名称" autofocus />
        </label>
        <label class="create-card__field">
          <span>摘要</span>
          <textarea v-model="createSummary" rows="3" placeholder="简短描述（可选）" />
        </label>
        <p v-if="createError" class="create-card__error">{{ createError }}</p>
        <div class="create-card__actions">
          <button type="button" class="create-card__cancel" @click="closeCreate">取消</button>
          <button type="submit" class="create-card__save" :disabled="!createName.trim() || isCreating">
            {{ isCreating ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.card-list {
  --mono: ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace;
  min-height: 100%;
  padding: 28px 28px 36px;
  background: var(--canvas-bg);
}

.card-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
}

.card-list__intro {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-list__intro h2 {
  margin: 0;
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.card-list__hint {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
  max-width: 36rem;
}

.card-list__hint--block {
  margin-bottom: 8px;
}

.card-list__count {
  flex-shrink: 0;
  min-width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border-strong);
  background: var(--panel);
  color: var(--text-soft);
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.card-list__error {
  color: #dc2626;
  font-size: 13px;
}

.card-list__modal {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(28, 25, 23, 0.28);
}

.create-card {
  width: min(100%, 360px);
  padding: 20px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.create-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.create-card__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.create-card__field input,
.create-card__field textarea {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font: inherit;
  color: var(--text);
  resize: vertical;
}

.create-card__error {
  margin: 0;
  font-size: 12px;
  color: #dc2626;
}

.create-card__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.create-card__cancel,
.create-card__save {
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.create-card__cancel {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-soft);
}

.create-card__save {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
}

.create-card__save:disabled {
  opacity: 0.55;
  cursor: wait;
}

.card-list__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(272px, 1fr));
  gap: 16px;
}

/* ---------- 身份卡 ---------- */
.id-card {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 208px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.id-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
  transform: translateY(-3px);
}

/* 对角注册 / 裁切标记。 */
.id-card::before,
.id-card::after {
  content: '';
  position: absolute;
  width: 11px;
  height: 11px;
  z-index: 2;
  pointer-events: none;
  transition: border-color 0.2s ease;
}

.id-card::before {
  top: 9px;
  left: 9px;
  border-top: 1.5px solid var(--border-strong);
  border-left: 1.5px solid var(--border-strong);
}

.id-card::after {
  bottom: 9px;
  right: 9px;
  border-bottom: 1.5px solid var(--border-strong);
  border-right: 1.5px solid var(--border-strong);
}

.id-card:hover::before,
.id-card:hover::after {
  border-color: var(--text-soft);
}

/* 头部条：点阵纹理 + 等宽编号 + 芯片。 */
.id-card__band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 40px;
  padding: 0 14px 0 26px;
  border-bottom: 1px solid var(--border);
  background:
    radial-gradient(rgba(28, 25, 23, 0.08) 1px, transparent 1.4px) 0 0 / 9px 9px,
    linear-gradient(90deg, rgba(28, 25, 23, 0.03), rgba(28, 25, 23, 0.01));
}

.id-card__code {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--text-soft);
}

.id-card__chip {
  position: relative;
  width: 27px;
  height: 19px;
  border-radius: 4px;
  background: linear-gradient(135deg, rgba(28, 25, 23, 0.12), rgba(28, 25, 23, 0.04));
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

.id-card__chip::before {
  content: '';
  position: absolute;
  inset: 4px;
  background-image:
    linear-gradient(var(--border-strong), var(--border-strong)),
    linear-gradient(var(--border-strong), var(--border-strong));
  background-size: 100% 1px, 1px 100%;
  background-position: center, center;
  background-repeat: no-repeat;
  opacity: 0.65;
}

/* 主体行：头像 + 身份信息。 */
.id-card__main {
  flex: 1;
  display: flex;
  gap: 14px;
  padding: 16px 16px 12px;
}

.id-card__photo {
  position: relative;
  flex-shrink: 0;
  width: 66px;
  height: 82px;
  border-radius: 8px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 30% 22%, rgba(28, 25, 23, 0.06), transparent 60%),
    var(--paper);
  box-shadow:
    inset 0 0 0 1px var(--border),
    0 3px 8px rgba(28, 25, 23, 0.08);
  transition: box-shadow 0.2s ease;
}

.id-card:hover .id-card__photo {
  box-shadow:
    inset 0 0 0 1px var(--border-strong),
    0 5px 14px rgba(28, 25, 23, 0.12);
}

.id-card__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.id-card__initials {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text-soft);
}

.id-card__id {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-top: 1px;
}

.id-card__label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--muted);
}

.id-card__name {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.id-card__summary {
  margin: 3px 0 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-soft);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.id-card__summary--empty {
  color: var(--muted);
  font-style: italic;
}

.id-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.id-card__tag {
  font-family: var(--mono);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 3px 7px;
  border-radius: 5px;
  background: rgba(28, 25, 23, 0.05);
  color: var(--muted);
}

/* 底部：角色印章。 */
.id-card__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 11px 16px 13px 26px;
  border-top: 1px dashed var(--border);
}

.id-card__role {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(28, 25, 23, 0.04);
  color: var(--text-soft);
  box-shadow: inset 0 0 0 1px var(--border);
}

/* ---------- 新建卡片 ---------- */
.id-card--create {
  align-items: center;
  justify-content: center;
  gap: 11px;
  border-style: dashed;
  border-color: var(--border-strong);
  box-shadow: none;
  color: var(--muted);
  background:
    radial-gradient(rgba(28, 25, 23, 0.06) 1px, transparent 1.4px) 0 0 / 14px 14px,
    var(--panel);
}

.id-card--create:hover {
  color: var(--text);
  border-color: var(--text-soft);
  transform: translateY(-3px);
}

.id-card__create-photo {
  width: 66px;
  height: 82px;
  border-radius: 8px;
  border: 1.5px dashed var(--border-strong);
  display: grid;
  place-items: center;
  font-size: 30px;
  font-weight: 300;
  line-height: 1;
  color: var(--muted);
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease,
    transform 0.2s ease;
}

.id-card--create:hover .id-card__create-photo {
  border-style: solid;
  border-color: var(--text-soft);
  background: var(--panel);
  color: var(--text);
  transform: scale(1.04);
}

.id-card__create-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-soft);
}

.id-card--create:hover .id-card__create-label {
  color: var(--text);
}

.id-card__create-sub {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}
</style>
