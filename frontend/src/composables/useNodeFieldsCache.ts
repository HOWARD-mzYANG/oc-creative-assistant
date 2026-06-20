import type { DocFieldRow } from '../components/workspace/DocFieldsEditor.vue'
import { getNodeFields } from '../api/projectApi'

const cache = new Map<string, DocFieldRow[]>()

/** 封装 cacheKey 对应的组合式状态和操作。 */
function cacheKey(projectId: string, nodeId: string): string {
  return `${projectId}:${nodeId}`
}

/** 封装 cloneRows 对应的组合式状态和操作。 */
function cloneRows(rows: DocFieldRow[]): DocFieldRow[] {
  return rows.map((row) => ({ ...row }))
}

/** 封装 rowsFromFields 对应的组合式状态和操作。 */
function rowsFromFields(fields: Record<string, string>): DocFieldRow[] {
  const entries = Object.entries(fields)
  if (entries.length === 0) return [{ key: '', value: '' }]
  return entries.map(([key, value]) => ({ key, value }))
}

/** 封装 hasStoredFields 对应的组合式状态和操作。 */
function hasStoredFields(fields: Record<string, string>): boolean {
  return Object.entries(fields).some(
    ([key, value]) => key.trim() || value.trim(),
  )
}

/** 封装 useNodeFieldsCache 对应的组合式状态和操作。 */
export function useNodeFieldsCache() {
  /** 封装 get 对应的组合式状态和操作。 */
  function get(projectId: string, nodeId: string): DocFieldRow[] | undefined {
    const hit = cache.get(cacheKey(projectId, nodeId))
    return hit ? cloneRows(hit) : undefined
  }

  /** 封装 set 对应的组合式状态和操作。 */
  function set(projectId: string, nodeId: string, rows: DocFieldRow[]): void {
    cache.set(cacheKey(projectId, nodeId), cloneRows(rows))
  }

  /** 封装 invalidateNode 对应的组合式状态和操作。 */
  function invalidateNode(projectId: string, nodeId: string): void {
    cache.delete(cacheKey(projectId, nodeId))
  }

  /** 封装 prefetch 对应的组合式状态和操作。 */
  async function prefetch(projectId: string, nodeIds: string[]): Promise<void> {
    const pending = nodeIds.filter((id) => !cache.has(cacheKey(projectId, id)))
    if (!pending.length) return

    await Promise.all(
      pending.map(async (nodeId) => {
        try {
          const result = await getNodeFields(projectId, nodeId)
          if (hasStoredFields(result.fields)) {
            set(projectId, nodeId, rowsFromFields(result.fields))
          }
        } catch {
          /* 预取失败不影响主流程。 */
        }
      }),
    )
  }

  return { get, set, invalidateNode, prefetch }
}
