import { defineStore } from 'pinia'

/** 进入详情页时携带的节点初始快照（避免详情页再次发起 GET）。 */
export interface DetailNodeSnapshot {
  id: string
  title: string
  content: string
  nodeType: string
  typeLabel: string
  icon: string
  tags: string[]
  status: string
}

/**
 * 中央舞台状态（second_revision 变更 A）。
 *
 * 控制中央面板在“画布”和“节点详情”之间切换：双击节点进入详情，返回则回到画布。
 * 详情页占据画布位置，左右面板保持不变。
 */
export const useCenterStageStore = defineStore('centerStage', {
  state: () => ({
    mode: 'canvas' as 'canvas' | 'detail',
    detailNodeId: null as string | null,
    detailNode: null as DetailNodeSnapshot | null,
  }),
  actions: {
    /** 维护 store 中 openDetail 对应的状态变更。 */
    openDetail(nodeId: string, node?: DetailNodeSnapshot) {
      this.mode = 'detail'
      this.detailNodeId = nodeId
      this.detailNode = node ?? null
    },
    /** 维护 store 中 returnToCanvas 对应的状态变更。 */
    returnToCanvas() {
      this.mode = 'canvas'
      this.detailNodeId = null
      this.detailNode = null
    },
  },
})
