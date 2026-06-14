import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ProjectDetail } from '../types/project'
import { getProjectDetail } from '../api/projectApi'

/**
 * Current project store (first_revision decision 6).
 *
 * Holds the metadata of the currently open project: name / description / the three sub-graph ids / the latest seed.
 * The three workspace views (phase 3) get their corresponding graph_id from here.
 */
export const useProjectStore = defineStore('project', () => {
  const detail = ref<ProjectDetail | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  const plotGraphId = computed(() => detail.value?.plot_graph_id ?? null)
  const characterGraphId = computed(() => detail.value?.character_graph_id ?? null)
  const worldGraphId = computed(() => detail.value?.world_graph_id ?? null)

  /** Load the details of a given project; can force-refresh if it is already the current project. */
  async function loadProject(projectId: string, force = false): Promise<void> {
    if (!force && detail.value?.id === projectId) return
    isLoading.value = true
    error.value = ''
    try {
      detail.value = await getProjectDetail(projectId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '项目加载失败'
      detail.value = null
    } finally {
      isLoading.value = false
    }
  }

  /** Clear the current project (called when leaving the workspace). */
  function reset(): void {
    detail.value = null
    error.value = ''
  }

  return {
    detail,
    isLoading,
    error,
    plotGraphId,
    characterGraphId,
    worldGraphId,
    loadProject,
    reset,
  }
})
