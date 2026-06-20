import { defineStore } from 'pinia'

/** 世界观中央视图：文件夹笔记或层级树画布。 */
export const useWorldViewStore = defineStore('worldView', {
  state: () => ({
    mode: 'notes' as 'notes' | 'canvas',
  }),
  actions: {
    /** 维护 store 中 toggleMode 对应的状态变更。 */
    toggleMode() {
      this.mode = this.mode === 'notes' ? 'canvas' : 'notes'
    },
    /** 维护 store 中 setMode 对应的状态变更。 */
    setMode(mode: 'notes' | 'canvas') {
      this.mode = mode
    },
  },
})
