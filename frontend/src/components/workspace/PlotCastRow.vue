<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { loadSubgraph } from '../../api/graphApi'
import type { GraphNodeDto } from '../../api/graphApi'
import {
  createProjectEdge,
  deleteProjectEdge,
  getNodeCrossReferences,
  getNodeFields,
} from '../../api/projectApi'
import { useProjectStore } from '../../stores/useProjectStore'

interface CastMember {
  edgeId: string
  id: string
  title: string
  avatar: string
}

const props = defineProps<{
  projectId: string
  plotNodeId: string
}>()

const router = useRouter()
const projectStore = useProjectStore()
const { characterGraphId } = storeToRefs(projectStore)

const cast = ref<CastMember[]>([])
const allCharacters = ref<GraphNodeDto[]>([])
const avatarByCharacterId = ref<Record<string, string>>({})
const pickerOpen = ref(false)
const isLoading = ref(false)
const isLoadingCharacters = ref(false)

const linkedIds = computed(() => new Set(cast.value.map((member) => member.id)))
const pickableCharacters = computed(() =>
  allCharacters.value.filter((node) => !linkedIds.value.has(node.id)),
)

function closePicker() {
  pickerOpen.value = false
}

function onDocumentClick(event: MouseEvent) {
  if (!pickerOpen.value) return
  const target = event.target as HTMLElement
  if (!target.closest('.plot-cast__add-wrap')) {
    closePicker()
  }
}

async function readAvatar(nodeId: string): Promise<string> {
  try {
    const result = await getNodeFields(props.projectId, nodeId)
    return result.fields.avatar ?? ''
  } catch {
    return ''
  }
}

async function loadCharacterAvatars(nodeIds?: string[]) {
  const graphId = characterGraphId.value
  if (!graphId) {
    allCharacters.value = []
    avatarByCharacterId.value = {}
    return
  }

  isLoadingCharacters.value = true
  try {
    const graph = await loadSubgraph(graphId)
    allCharacters.value = graph.nodes
    const ids = nodeIds?.length ? nodeIds : graph.nodes.map((node) => node.id)
    const pairs = await Promise.all(
      ids.map(async (id) => [id, await readAvatar(id)] as const),
    )
    const next = { ...avatarByCharacterId.value }
    for (const [id, avatar] of pairs) {
      next[id] = avatar
    }
    avatarByCharacterId.value = next
  } catch {
    allCharacters.value = []
  } finally {
    isLoadingCharacters.value = false
  }
}

async function loadCast() {
  isLoading.value = true
  try {
    const response = await getNodeCrossReferences(props.projectId, props.plotNodeId)
    const characterRefs = response.references.filter((ref) => ref.other_section === 'character')
    await loadCharacterAvatars(characterRefs.map((ref) => ref.other_node_id))
    cast.value = characterRefs.map((ref) => ({
      edgeId: ref.edge_id,
      id: ref.other_node_id,
      title: ref.other_title,
      avatar: avatarByCharacterId.value[ref.other_node_id] ?? '',
    }))
  } catch {
    cast.value = []
  } finally {
    isLoading.value = false
  }
}

async function loadCharacters() {
  await loadCharacterAvatars()
}

async function linkCharacter(characterId: string) {
  const character = allCharacters.value.find((node) => node.id === characterId)
  if (!character) return

  await createProjectEdge(props.projectId, {
    id: `plot-cast-${props.plotNodeId}-${characterId}`,
    source: props.plotNodeId,
    target: characterId,
    label: '',
    relationType: 'relates_to',
  })
  closePicker()
  await loadCast()
}

async function unlinkCharacter(edgeId: string) {
  await deleteProjectEdge(props.projectId, edgeId)
  await loadCast()
}

function openCharacter(characterId: string) {
  router.push(`/workspace/${props.projectId}/characters/${characterId}`)
}

function togglePicker() {
  pickerOpen.value = !pickerOpen.value
  if (pickerOpen.value) void loadCharacters()
}

function markAvatarBroken(characterId: string) {
  avatarByCharacterId.value = { ...avatarByCharacterId.value, [characterId]: '' }
  cast.value = cast.value.map((member) =>
    member.id === characterId ? { ...member, avatar: '' } : member,
  )
}

onMounted(async () => {
  await projectStore.loadProject(props.projectId)
  document.addEventListener('click', onDocumentClick)
  void loadCast()
  void loadCharacters()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})

watch(
  characterGraphId,
  (id) => {
    if (id) void loadCharacters()
  },
)

watch(
  () => props.plotNodeId,
  () => {
    closePicker()
    void loadCast()
    void loadCharacters()
  },
)
</script>

<template>
  <section class="plot-cast">
    <div class="plot-cast__head">
      <span class="eyebrow">参与者</span>
      <span v-if="isLoading" class="plot-cast__hint">加载中…</span>
    </div>

    <div class="plot-cast__row">
      <button
        v-for="member in cast"
        :key="member.edgeId"
        type="button"
        class="plot-cast__avatar"
        :title="member.title"
        @click="openCharacter(member.id)"
      >
        <img
          v-if="member.avatar"
          :src="member.avatar"
          :alt="member.title"
          @error="markAvatarBroken(member.id)"
        />
        <svg v-else class="plot-cast__placeholder" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="8" r="4" />
          <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
        </svg>
        <span
          class="plot-cast__remove"
          role="button"
          aria-label="移除参与者"
          @click.stop="unlinkCharacter(member.edgeId)"
        >
          ×
        </span>
      </button>

      <div class="plot-cast__add-wrap">
        <button
          type="button"
          class="plot-cast__add"
          aria-label="添加参与者"
          title="添加参与者"
          @click="togglePicker"
        >
          +
        </button>

        <div v-if="pickerOpen" class="plot-cast__picker">
          <p v-if="isLoadingCharacters" class="plot-cast__picker-empty">正在加载角色…</p>
          <p v-else-if="allCharacters.length === 0" class="plot-cast__picker-empty">
            还没有角色，请先在“角色”中创建。
          </p>
          <p v-else-if="pickableCharacters.length === 0" class="plot-cast__picker-empty">
            All characters are already linked.
          </p>
          <button
            v-for="character in pickableCharacters"
            :key="character.id"
            type="button"
            class="plot-cast__picker-item"
            @click="linkCharacter(character.id)"
          >
            <span class="plot-cast__picker-avatar">
              <img
                v-if="avatarByCharacterId[character.id]"
                :src="avatarByCharacterId[character.id]"
                :alt="character.title"
              />
              <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
              </svg>
            </span>
            <span class="plot-cast__picker-name">{{ character.title }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.plot-cast {
  width: 100%;
  padding-top: 20px;
  border-top: 1px solid rgba(28, 25, 23, 0.08);
  overflow: visible;
}

.plot-cast__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.plot-cast__hint {
  font-size: 12px;
  color: var(--muted);
}

.plot-cast__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.plot-cast__avatar {
  position: relative;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
  background: var(--panel-strong);
  cursor: pointer;
}

.plot-cast__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.plot-cast__placeholder {
  width: 58%;
  height: 58%;
  fill: var(--muted);
}

.plot-cast__remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(28, 25, 23, 0.72);
  color: #fff;
  font-size: 12px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.plot-cast__avatar:hover .plot-cast__remove {
  opacity: 1;
}

.plot-cast__add-wrap {
  position: relative;
}

.plot-cast__add {
  width: 52px;
  height: 52px;
  border: 1px dashed var(--border-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease,
    background 0.15s ease;
}

.plot-cast__add:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}

.plot-cast__picker {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  z-index: 30;
  min-width: 240px;
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-strong);
  box-shadow: var(--shadow-md);
}

.plot-cast__picker-empty {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--muted);
}

.plot-cast__picker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}

.plot-cast__picker-item:hover {
  background: var(--accent-soft);
  color: var(--accent-deep);
}

.plot-cast__picker-avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: var(--panel-strong);
  border: 1px solid var(--border);
}

.plot-cast__picker-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.plot-cast__picker-avatar svg {
  width: 62%;
  height: 62%;
  fill: var(--muted);
}

.plot-cast__picker-name {
  font-weight: 600;
}
</style>
