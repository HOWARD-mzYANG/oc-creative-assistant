<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

onMounted(async () => {
  await library.fetchProjects()
  if (projects.value.length > 0) {
    selectedId.value = projects.value[0].id
  }
})

function enterChat(): void {
  if (!selectedId.value) return
  router.push(`/chat/${selectedId.value}`)
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
          <select v-model="selectedId" :disabled="projects.length === 0">
            <option v-if="projects.length === 0" value="">（还没有项目，请先创建）</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">
              {{ project.name }}
            </option>
          </select>
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
.chat-entry__field select {
  padding: 8px 10px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  font: inherit;
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
