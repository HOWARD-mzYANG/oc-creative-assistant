const cache = new Map<string, string>()

/** 封装 cacheKey 对应的组合式状态和操作。 */
function cacheKey(projectId: string, nodeId: string): string {
  return `${projectId}:${nodeId}`
}

/** 封装 useCharacterAvatarCache 对应的组合式状态和操作。 */
export function useCharacterAvatarCache() {
  /** 封装 get 对应的组合式状态和操作。 */
  function get(projectId: string, nodeId: string): string {
    return cache.get(cacheKey(projectId, nodeId)) ?? ''
  }

  /** 封装 set 对应的组合式状态和操作。 */
  function set(projectId: string, nodeId: string, avatar: string): void {
    if (avatar) {
      cache.set(cacheKey(projectId, nodeId), avatar)
    } else {
      cache.delete(cacheKey(projectId, nodeId))
    }
  }

  /** 封装 snapshot 对应的组合式状态和操作。 */
  function snapshot(projectId: string): Record<string, string> {
    const prefix = `${projectId}:`
    const next: Record<string, string> = {}
    for (const [key, avatar] of cache.entries()) {
      if (!key.startsWith(prefix)) continue
      next[key.slice(prefix.length)] = avatar
    }
    return next
  }

  return { get, set, snapshot }
}
