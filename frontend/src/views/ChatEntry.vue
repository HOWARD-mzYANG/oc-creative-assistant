<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useLibraryStore } from '../stores/useLibraryStore'

/**
 * 对话入口（第 2 阶段）。
 *
 * 通过下拉框选择已有项目，也可新建项目；确认后跳转到 /chat/:projectId。
 * 复用 useLibraryStore，与项目库共享项目列表和创建逻辑。
 */
const router = useRouter()
const library = useLibraryStore()
const { projects, isLoading, error } = storeToRefs(library)

const selectedId = ref('')
const isCreating = ref(false)
const newName = ref('')
const isProjectMenuOpen = ref(false)
const projectSelectEl = ref<HTMLElement | null>(null)

const selectedProjectName = computed(() => {
  if (projects.value.length === 0) return '（还没有项目，请先创建）'
  return projects.value.find((project) => project.id === selectedId.value)?.name ?? '选择项目'
})

onMounted(async () => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  await library.fetchProjects()
  if (projects.value.length > 0) {
    selectedId.value = projects.value[0].id
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})

function enterChat(): void {
  if (!selectedId.value) return
  router.push(`/chat/${selectedId.value}`)
}

function toggleProjectMenu(): void {
  if (projects.value.length === 0) return
  isProjectMenuOpen.value = !isProjectMenuOpen.value
}

function selectProject(projectId: string): void {
  selectedId.value = projectId
  isProjectMenuOpen.value = false
}

function handleDocumentPointerDown(event: PointerEvent): void {
  const target = event.target
  if (!(target instanceof Node)) return
  if (!projectSelectEl.value?.contains(target)) {
    isProjectMenuOpen.value = false
  }
}

async function handleCreate(): Promise<void> {
  const name = newName.value.trim()
  if (!name) return
  const detail = await library.createProject({ name })
  isCreating.value = false
  newName.value = ''
  router.push(`/chat/${detail.id}`)
}
</script>

<template>
  <main class="chat-entry">
    <button type="button" class="chat-entry__back" @click="router.push('/')">← 首页</button>
    <div class="chat-entry__panel">
      <h1>开始一场对话</h1>

      <p v-if="error" class="chat-entry__error">{{ error }}</p>
      <p v-else-if="isLoading" class="chat-entry__hint">正在加载项目…</p>

      <template v-else>
        <label class="chat-entry__field">
          <span>选择项目</span>
          <div
            ref="projectSelectEl"
            class="chat-entry__custom-select"
            :class="{ 'is-disabled': projects.length === 0 }"
            @keydown.escape.stop="isProjectMenuOpen = false"
          >
            <button
              type="button"
              class="chat-entry__select-trigger"
              :class="{ 'is-open': isProjectMenuOpen }"
              :disabled="projects.length === 0"
              aria-haspopup="listbox"
              :aria-expanded="isProjectMenuOpen"
              @click="toggleProjectMenu"
            >
              <span class="chat-entry__select-value">{{ selectedProjectName }}</span>
              <span class="chat-entry__select-arrow" aria-hidden="true"></span>
            </button>

            <ul v-if="isProjectMenuOpen" class="chat-entry__select-options" role="listbox">
              <li
                v-for="project in projects"
                :key="project.id"
                role="option"
                :aria-selected="project.id === selectedId"
              >
                <button
                  type="button"
                  class="chat-entry__select-option"
                  :class="{ 'is-selected': project.id === selectedId }"
                  @click="selectProject(project.id)"
                >
                  <span>{{ project.name }}</span>
                  <span v-if="project.id === selectedId" class="chat-entry__select-check">已选</span>
                </button>
              </li>
            </ul>
          </div>
        </label>

        <div class="chat-entry__actions">
          <button type="button" class="primary" :disabled="!selectedId" @click="enterChat">
            进入对话
          </button>
          <button type="button" @click="isCreating = true">+ 新建项目</button>
        </div>
      </template>

      <div v-if="isCreating" class="chat-entry__create">
        <input v-model="newName" type="text" placeholder="新项目名称" />
        <button type="button" class="primary" :disabled="!newName.trim()" @click="handleCreate">
          创建并进入
        </button>
        <button type="button" @click="isCreating = false">取消</button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.chat-entry {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.chat-entry__back {
  position: absolute;
  top: 24px;
  left: 32px;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border, #ddd);
  background: var(--app-bg, #fff);
  cursor: pointer;
}
.chat-entry__panel {
  width: 380px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 32px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 16px;
}
.chat-entry__panel h1 {
  font-size: 22px;
}
.chat-entry__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
}
.chat-entry__custom-select {
  position: relative;
  width: 100%;
}
.chat-entry__select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: 42px;
  padding: 9px 12px;
  border: 1px solid var(--border, #ddd);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.96)),
    var(--panel, #fff);
  color: var(--text, #111827);
  font: inherit;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    background-color 0.16s ease;
}
.chat-entry__select-trigger:hover:not(:disabled) {
  border-color: var(--accent, #6366f1);
}
.chat-entry__select-trigger:focus,
.chat-entry__select-trigger.is-open {
  outline: none;
  border-color: var(--accent, #6366f1);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent, #6366f1) 18%, transparent);
}
.chat-entry__select-trigger:disabled {
  color: var(--muted, #8a8f98);
  cursor: not-allowed;
  opacity: 0.72;
}
.chat-entry__select-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-entry__select-arrow {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted, #8a8f98);
  border-bottom: 2px solid var(--muted, #8a8f98);
  transform: translateY(-2px) rotate(45deg);
  transition: transform 0.16s ease;
}
.chat-entry__select-trigger.is-open .chat-entry__select-arrow {
  transform: translateY(2px) rotate(225deg);
}
.chat-entry__custom-select.is-disabled .chat-entry__select-arrow {
  opacity: 0.5;
}
.chat-entry__select-options {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 20;
  max-height: 240px;
  margin: 0;
  padding: 6px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  background: var(--panel, #fff);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.14), 0 4px 12px rgba(15, 23, 42, 0.08);
}
.chat-entry__select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text, #111827);
  font: inherit;
  cursor: pointer;
  text-align: left;
}
.chat-entry__select-option:hover,
.chat-entry__select-option:focus {
  outline: none;
  background: var(--accent-soft, #eef2ff);
}
.chat-entry__select-option.is-selected {
  color: var(--accent, #6366f1);
  font-weight: 600;
}
.chat-entry__select-check {
  flex: 0 0 auto;
  color: var(--accent, #6366f1);
  font-size: 12px;
}
.chat-entry__actions,
.chat-entry__create {
  display: flex;
  gap: 8px;
}
.chat-entry__create {
  flex-wrap: wrap;
}
.chat-entry__create input {
  flex: 1 1 100%;
  padding: 8px 10px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  font: inherit;
}
.chat-entry__actions button,
.chat-entry__create button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--border, #ddd);
  background: var(--app-bg, #fff);
  cursor: pointer;
}
.primary {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
  color: #fff;
}
.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.chat-entry__error {
  color: #dc2626;
}
.chat-entry__hint {
  color: #888;
}
</style>
