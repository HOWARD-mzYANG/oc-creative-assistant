<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useLibraryStore } from '../stores/useLibraryStore'
import type { ProjectSummary } from '../types/project'

/**
 * 项目库（第 2 阶段）。
 *
 * 纵向排列的横向条带卡片：白色渐变配黑色文字，
 * 右侧可显示渐隐封面，右上角提供删除入口。
 * 点击卡片会打开工作区。
 */
const router = useRouter()
const library = useLibraryStore()
const { projects, isLoading, error } = storeToRefs(library)

const isCreating = ref(false)
const newName = ref('')
const newDescription = ref('')

onMounted(() => {
  library.fetchProjects()
})

/** 打开目标视图或弹层。 */
function openProject(projectId: string): void {
  router.push(`/workspace/${projectId}`)
}

/** 处理对应的用户交互或组件事件。 */
async function handleCreate(): Promise<void> {
  const name = newName.value.trim()
  if (!name) return
  const detail = await library.createProject({
    name,
    description: newDescription.value.trim(),
  })
  isCreating.value = false
  newName.value = ''
  newDescription.value = ''
  router.push(`/workspace/${detail.id}`)
}

/** 处理对应的用户交互或组件事件。 */
async function handleDelete(projectId: string, event: MouseEvent): Promise<void> {
  event.stopPropagation()
  await library.removeProject(projectId)
}

/** 格式化数据为界面展示所需的文本。 */
function formatTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString()
}

/** 白色渐变遮罩；存在封面图时在右侧渐隐显示。 */
function stripBackground(project: ProjectSummary): string {
  if (project.cover_image) {
    return (
      'linear-gradient(to right, ' +
      '#ffffff 0%, #ffffff 30%, ' +
      'rgba(255, 255, 255, 0.94) 52%, ' +
      'rgba(255, 255, 255, 0.62) 76%, ' +
      'rgba(255, 255, 255, 0.2) 100%), ' +
      `url("${project.cover_image}")`
    )
  }
  return 'linear-gradient(110deg, #ffffff 0%, #fafafa 55%, #f3f1f8 100%)'
}
</script>

<template>
  <main class="library">
    <header class="library__header">
      <button type="button" class="library__back" @click="router.push('/')">← 首页</button>
      <h1>项目库</h1>
      <button type="button" class="library__new" @click="isCreating = true">+ 新建项目</button>
    </header>

    <p v-if="error" class="library__error">{{ error }}</p>
    <p v-else-if="isLoading" class="library__hint">加载中…</p>
    <p v-else-if="projects.length === 0" class="library__hint">还没有项目，请从右上角创建一个。</p>

    <section v-else class="library__list">
      <article
        v-for="project in projects"
        :key="project.id"
        class="strip"
        :style="{ backgroundImage: stripBackground(project) }"
        @click="openProject(project.id)"
      >
        <button
          type="button"
          class="strip__del"
          aria-label="删除项目"
          title="删除项目"
          @click="handleDelete(project.id, $event)"
        >
          删除
        </button>
        <div class="strip__panel">
          <h3 class="strip__name">{{ project.name }}</h3>
          <p class="strip__desc">{{ project.description || '暂无描述' }}</p>
          <footer class="strip__footer">
            <span class="strip__time">{{ formatTime(project.updated_at) }}</span>
          </footer>
        </div>
      </article>
    </section>

    <div v-if="isCreating" class="library__modal" @click.self="isCreating = false">
      <div class="library__dialog">
        <h2>新建项目</h2>
        <input v-model="newName" type="text" placeholder="项目名称" />
        <textarea v-model="newDescription" placeholder="描述（可选）" rows="3"></textarea>
        <div class="library__dialog-actions">
          <button type="button" @click="isCreating = false">取消</button>
          <button type="button" class="primary" :disabled="!newName.trim()" @click="handleCreate">
            创建
          </button>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
.library {
  box-sizing: border-box;
  width: 100%;
  min-height: 100vh;
  padding: 24px 32px;
}
.library__header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}
.library__header h1 {
  flex: 1;
  font-size: 22px;
}
.library__back,
.library__new {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border, #ddd);
  background: var(--app-bg, #fff);
  cursor: pointer;
}
.library__new {
  border-color: var(--accent);
  color: var(--accent);
}
.library__hint,
.library__error {
  color: #888;
}
.library__error {
  color: #dc2626;
}
.library__list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
}
.strip {
  position: relative;
  width: 100%;
  min-height: 132px;
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border, #e5e7eb);
  background-color: #fff;
  background-repeat: no-repeat;
  background-position: right center;
  background-size: cover;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.strip:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border, #e5e7eb));
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.1);
}
.strip__panel {
  width: min(58%, 640px);
  min-width: 240px;
  min-height: inherit;
  padding: 18px 88px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text, #111);
}
.strip__name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text, #111);
}
.strip__desc {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-soft, #4b5563);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.strip__footer {
  display: flex;
  align-items: center;
}
.strip__time {
  font-size: 12px;
  color: var(--muted, #6b7280);
}
.strip__del {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft, #4b5563);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  padding: 5px 11px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}
.strip__del:hover {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}
.library__modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
}
.library__dialog {
  background: var(--app-bg, #fff);
  border-radius: 12px;
  padding: 24px;
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.library__dialog input,
.library__dialog textarea {
  padding: 8px 10px;
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  font: inherit;
  resize: vertical;
}
.library__dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.library__dialog-actions button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--border, #ddd);
  background: var(--app-bg, #fff);
  cursor: pointer;
}
.library__dialog-actions .primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.library__dialog-actions .primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
