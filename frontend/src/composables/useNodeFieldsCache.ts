import type { DocFieldRow } from '../components/workspace/DocFieldsEditor.vue'
import { getNodeFields } from '../api/projectApi'

const cache = new Map<string, DocFieldRow[]>()

function cacheKey(projectId: string, nodeId: string): string {
  return `${projectId}:${nodeId}`
}

function cloneRows(rows: DocFieldRow[]): DocFieldRow[] {
  return rows.map((row) => ({ ...row }))
}

function rowsFromFields(fields: Record<string, string>): DocFieldRow[] {
  const entries = Object.entries(fields)
  if (entries.length === 0) return [{ key: '', value: '' }]
  return entries.map(([key, value]) => ({ key, value }))
}

function hasStoredFields(fields: Record<string, string>): boolean {
  return Object.entries(fields).some(
    ([key, value]) => key.trim() || value.trim(),
  )
}

export function useNodeFieldsCache() {
  function get(projectId: string, nodeId: string): DocFieldRow[] | undefined {
    const hit = cache.get(cacheKey(projectId, nodeId))
    return hit ? cloneRows(hit) : undefined
  }

  function set(projectId: string, nodeId: string, rows: DocFieldRow[]): void {
    cache.set(cacheKey(projectId, nodeId), cloneRows(rows))
  }

  function invalidateNode(projectId: string, nodeId: string): void {
    cache.delete(cacheKey(projectId, nodeId))
  }

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
