import { defineStore } from 'pinia'

export type WebSearchMode = 'auto' | 'on' | 'off'

/** 底部对话框中引用的节点（second_revision 变更 C）。 */
export interface QuotedNodeRef {
  id: string
  type: string // 'character' | 'plot' | 'world' ...
  title: string
}

/**
 * 底部输入器状态：引用节点卡片 + 输入框文本。
 *
 * 选中节点 -> 复制到对话框 -> 在输入框上方显示为可移除的小卡片。
 */
export const useComposerStore = defineStore('composer', {
  state: () => ({
    references: [] as QuotedNodeRef[],
    input: '',
    collapsed: false,
    /** auto = 启发式判断；on = 强制联网搜索；off = 禁用联网搜索。 */
    webSearchMode: 'auto' as WebSearchMode,
  }),
  actions: {
    cycleWebSearchMode() {
      const order: WebSearchMode[] = ['auto', 'on', 'off']
      const index = order.indexOf(this.webSearchMode)
      this.webSearchMode = order[(index + 1) % order.length]
    },
    addReferences(refs: QuotedNodeRef[]) {
      const existing = new Set(this.references.map((r) => r.id))
      refs.forEach((r) => {
        if (!existing.has(r.id)) this.references.push(r)
      })
    },
    removeReference(id: string) {
      this.references = this.references.filter((r) => r.id !== id)
    },
    setCollapsed(value: boolean) {
      this.collapsed = value
    },
    clear() {
      this.references = []
      this.input = ''
    },
  },
})
