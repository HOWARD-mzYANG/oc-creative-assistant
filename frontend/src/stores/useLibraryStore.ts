import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProjectCreatePayload, ProjectDetail, ProjectSummary } from '../types/project'
import {
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
  listProjects,
} from '../api/projectApi'

/**
 * 项目库状态仓库（first_revision 决策 6）。
 *
 * 处理跨路由共享的项目列表和 CRUD。单个画布内的细粒度操作仍由 composables 负责。
 */
export const useLibraryStore = defineStore('library', () => {
  const projects = ref<ProjectSummary[]>([])
  const isLoading = ref(false)
  const error = ref('')

  /** 从后端获取所有项目。 */
  async function fetchProjects(): Promise<void> {
    isLoading.value = true
    error.value = ''
    try {
      projects.value = await listProjects()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '项目列表加载失败'
      projects.value = []
    } finally {
      isLoading.value = false
    }
  }

  /** 创建项目（后端会自动创建三个子图），成功后刷新列表。 */
  async function createProject(payload: ProjectCreatePayload): Promise<ProjectDetail> {
    const detail = await apiCreateProject(payload)
    await fetchProjects()
    return detail
  }

  /** 删除项目，成功后刷新列表。 */
  async function removeProject(projectId: string): Promise<void> {
    await apiDeleteProject(projectId)
    await fetchProjects()
  }

  return { projects, isLoading, error, fetchProjects, createProject, removeProject }
})
