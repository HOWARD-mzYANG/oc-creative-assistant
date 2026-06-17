import { defineStore } from 'pinia'

/** 跨页面“跳转到节点”意图：聊天里的引用芯片写入它，目标画布加载后消费它。 */
export const useNodeNavStore = defineStore('nodeNav', {
  state: () => ({ pendingNodeId: '' }),
  actions: {
    request(nodeId: string) {
      this.pendingNodeId = nodeId
    },
    consume(): string {
      const id = this.pendingNodeId
      this.pendingNodeId = ''
      return id
    },
  },
})
