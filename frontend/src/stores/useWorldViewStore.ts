import { defineStore } from 'pinia'

/** 世界观中央视图：文件夹笔记或层级树画布。 */
export const useWorldViewStore = defineStore('worldView', {
  state: () => ({
    mode: 'notes' as 'notes' | 'canvas',
  }),
  actions: {
    toggleMode() {
      this.mode = this.mode === 'notes' ? 'canvas' : 'notes'
    },
    setMode(mode: 'notes' | 'canvas') {
      this.mode = mode
    },
  },
})
