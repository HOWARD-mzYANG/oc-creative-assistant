import { ref } from 'vue'
import type { IndexingStatusDto } from '../api/graphApi'

/**
 * 集中处理后端 embedding / ChromaDB 同步状态的翻译与展示。
 *
 * 状态栏（indexState）展示短句；警告条（indexingAlert）把详细原因整理成用户可处理的提示，
 * 避免直接把完整 API 错误 JSON 暴露到界面上。
 */
export function useIndexingStatus() {
  const indexingStatus = ref<IndexingStatusDto | undefined>()
  const indexingAlert = ref('')
  const indexState = ref('向量索引未检查')

  function simplifyError(error?: string | null) {
    if (!error) {
      return '请检查 backend/.env 中的 embedding 配置。'
    }
    if (error.includes('invalid_api_key') || error.includes('Incorrect API key') || error.includes('401')) {
      return 'API Key 无效。'
    }
    if (error.toLowerCase().includes('timeout')) {
      return 'embedding 服务请求超时，请稍后重试。'
    }
    if (error.includes('Connection') || error.includes('connect') || error.includes('network')) {
      return '无法连接 embedding 服务，请检查网络或 base_url。'
    }
    return error.length > 120 ? `${error.slice(0, 120)}...` : error
  }

  function formatState(indexing?: IndexingStatusDto) {
    if (!indexing || indexing.status === 'not_checked') {
      return '向量索引未检查'
    }
    if (indexing.status === 'synced') {
      return `向量索引已同步 ${indexing.indexed_nodes}/${indexing.expected_nodes}`
    }
    return indexing.status === 'failed'
      ? `向量索引失败 ${indexing.indexed_nodes}/${indexing.expected_nodes}`
      : `向量索引不完整 ${indexing.indexed_nodes}/${indexing.expected_nodes}`
  }

  function formatAlert(indexing: IndexingStatusDto) {
    const problem = simplifyError(indexing.error)
    const missingCount = indexing.missing_node_ids.length
    const missingText = missingCount > 0 ? `目前还有 ${missingCount} 个节点缺少可用向量。` : ''
    return `SQLite 已保存，但向量索引${indexing.status === 'failed' ? '失败' : '不完整'}。${problem} ${missingText}`.trim()
  }

  function applyIndexingStatus(indexing?: IndexingStatusDto) {
    indexingStatus.value = indexing
    indexState.value = formatState(indexing)
    if (!indexing || indexing.status === 'not_checked' || indexing.status === 'synced') {
      indexingAlert.value = ''
      return
    }
    indexingAlert.value = formatAlert(indexing)
  }

  function dismissAlert() {
    indexingAlert.value = ''
  }

  return {
    indexingStatus,
    indexingAlert,
    indexState,
    applyIndexingStatus,
    dismissAlert,
  }
}
