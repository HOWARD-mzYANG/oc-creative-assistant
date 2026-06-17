import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ProjectDetail } from '../types/project'
import { getProjectDetail } from '../api/projectApi'

/**
 * 当前项目状态仓库（first_revision 决策 6）。
 *
 * 保存当前打开项目的元数据：名称、描述、三个子图 ID 和最新 seed。
 * 工作区三个视图（第 3 阶段）从这里读取各自的 graph_id。
 */
export const useProjectStore = defineStore('project', () => {
  const detail = ref<ProjectDetail | null>(null)
  const isLoading = ref(false)
  const error = ref('')

  const plotGraphId = computed(() => detail.value?.plot_graph_id ?? null)
  const characterGraphId = computed(() => detail.value?.character_graph_id ?? null)
  const worldGraphId = computed(() => detail.value?.world_graph_id ?? null)

  /** 加载指定项目详情；如果它已经是当前项目，也可以强制刷新。 */
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

  /** 清空当前项目（离开工作区时调用）。 */
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
