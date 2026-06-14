<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { exportProjectOc, importProjectOc, getProjectExport } from '../../api/projectApi'
import { openProjectPdf } from '../../utils/projectExport'
import { useProjectStore } from '../../stores/useProjectStore'

defineProps<{
  variant?: 'default' | 'sidebar'
}>()

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const ocInput = ref<HTMLInputElement | null>(null)
const menuOpen = ref(false)

function currentProjectId(): string {
  return String(route.params.projectId || projectStore.detail?.id || '')
}

async function onExportOc() {
  const projectId = currentProjectId()
  if (!projectId) return
  const blob = await exportProjectOc(projectId)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${projectStore.detail?.name || 'project'}.oc`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function onExportPdf() {
  const projectId = currentProjectId()
  if (!projectId) return
  const data = await getProjectExport(projectId)
  await openProjectPdf(data)
}

function choose(format: 'oc' | 'pdf') {
  menuOpen.value = false
  if (format === 'oc') void onExportOc()
  else void onExportPdf()
}

async function onImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const { id } = await importProjectOc(file)
    router.push(`/workspace/${id}`)
  } finally {
    input.value = ''
  }
}
</script>

<template>
  <span class="project-io" :class="{ 'project-io--sidebar': variant === 'sidebar' }">
    <input ref="ocInput" type="file" accept=".oc,application/json" hidden @change="onImport" />
    <button type="button" class="project-io__btn" @click="ocInput?.click()">导入</button>
    <span class="project-io__export">
      <button type="button" class="project-io__btn" @click="menuOpen = !menuOpen">导出</button>
      <template v-if="menuOpen">
        <div class="project-io__backdrop" @click="menuOpen = false" />
        <ul
          class="project-io__menu"
          :class="{ 'project-io__menu--up': variant === 'sidebar' }"
        >
          <li><button type="button" @click="choose('oc')">.oc 文件</button></li>
          <li><button type="button" @click="choose('pdf')">PDF</button></li>
        </ul>
      </template>
    </span>
  </span>
</template>

<style scoped>
.project-io {
  display: inline-flex;
  gap: 8px;
}

.project-io--sidebar {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  width: 100%;
}

.project-io__btn {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.project-io__btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.project-io--sidebar .project-io__export {
  width: 100%;
  min-width: 0;
}

.project-io--sidebar .project-io__btn {
  width: 100%;
  padding: 9px 10px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  border-radius: 9px;
  border-color: var(--border);
  background: rgba(255, 255, 255, 0.55);
  color: var(--muted);
}

.project-io--sidebar .project-io__btn:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent-deep);
}

.project-io__export {
  position: relative;
  display: inline-flex;
}

.project-io__backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
}

.project-io__menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  z-index: 41;
  min-width: 120px;
  padding: 4px;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow-lg, 0 6px 18px rgba(0, 0, 0, 0.14));
}

.project-io__menu--up {
  top: auto;
  bottom: 100%;
  margin-top: 0;
  margin-bottom: 6px;
}

.project-io__menu li {
  margin: 0;
}

.project-io__menu button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  font-size: 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.project-io__menu button:hover {
  background: var(--accent-soft, rgba(139, 92, 246, 0.12));
  color: var(--accent);
}
</style>
