import { defineStore } from 'pinia'

/** 工作区右侧面板中的单张 AI 输出卡片（second_revision 变更 B）。 */
export interface AiOutput {
  id: string
  type: 'search' | 'rag' | 'question' | 'feedback'
  content: string
  timestamp: number
  collapsed: boolean
  metadata?: Record<string, unknown>
}

/**
 * 右侧面板 AI 输出流：时间线卡片按时间顺序排列（最旧在上）。
 *
 * 工作区智能体被动响应；输出会按类型分发到不同卡片并追加展示（W5 接入 SSE）。
 */
export const useAiOutputStore = defineStore('aiOutput', {
  state: () => ({
    outputs: [] as AiOutput[],
  }),
  actions: {
    /** 维护 store 中 push 对应的状态变更。 */
    push(output: Omit<AiOutput, 'id' | 'timestamp' | 'collapsed'>) {
      this.outputs.push({
        ...output,
        id: crypto.randomUUID(),
        timestamp: Date.now(),
        collapsed: false,
      })
    },
    /** 维护 store 中 toggleCollapse 对应的状态变更。 */
    toggleCollapse(id: string) {
      const o = this.outputs.find((x) => x.id === id)
      if (o) o.collapsed = !o.collapsed
    },
    /** 维护 store 中 clear 对应的状态变更。 */
    clear() {
      this.outputs = []
    },
  },
})
