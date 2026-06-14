import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProjectCreatePayload, ProjectDetail, ProjectSummary } from '../types/project'
import {
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
  listProjects,
} from '../api/projectApi'

/**
 * Project library store (first_revision decision 6).
 *
 * Handles the cross-route shared project list and CRUD. Fine-grained operations within a single canvas are still handled by composables.
 */
export const useLibraryStore = defineStore('library', () => {
  const projects = ref<ProjectSummary[]>([])
  const isLoading = ref(false)
  const error = ref('')

  /** Fetch all projects from the backend. */
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

  /** Create a project (the backend auto-creates three sub-graphs), then refresh the list on success. */
  async function createProject(payload: ProjectCreatePayload): Promise<ProjectDetail> {
    const detail = await apiCreateProject(payload)
    await fetchProjects()
    return detail
  }

  /** Delete a project, then refresh the list on success. */
  async function removeProject(projectId: string): Promise<void> {
    await apiDeleteProject(projectId)
    await fetchProjects()
  }

  return { projects, isLoading, error, fetchProjects, createProject, removeProject }
})
