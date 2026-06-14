import { defineStore } from 'pinia'

/** 世界观 center view: folder notes or hierarchy tree canvas. */
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
