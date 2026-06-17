<script setup lang="ts">
import { useCenterStageStore } from '../../stores/useCenterStageStore'

/**
 * 中央舞台控制器（second_revision 变更 A）。
 *
 * W1 中是占位组件。W3 时会根据 useCenterStageStore.mode 在画布和节点详情间切换：
 *   <CanvasWorkspace v-if="mode==='canvas'" /> ⇄ <NodeDetailView v-else />
 * 当前画布视图仍由各子图路由视图（PlotCanvas / WorldCanvas）直接渲染；
 * W3 在这里接入双击进入详情的能力。
 */
const store = useCenterStageStore()
defineExpose({ store })
</script>

<template>
  <div class="center-stage">
    <slot />
  </div>
</template>

<style scoped>
.center-stage {
  height: 100%;
  min-height: 0;
}
</style>
