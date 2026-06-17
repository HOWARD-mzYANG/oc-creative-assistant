<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useProjectStore } from '../../stores/useProjectStore'
import SubgraphCanvas from '../../components/workspace/SubgraphCanvas.vue'

/**
 * 故事视图（first_revision 第 3 阶段）：绑定到情节子图的 Vue Flow 画布。
 */
const { plotGraphId } = storeToRefs(useProjectStore())
</script>

<template>
  <SubgraphCanvas
    v-if="plotGraphId"
    :key="plotGraphId"
    :graph-id="plotGraphId"
    :create-types="['plot']"
  />
  <p v-else class="workspace-loading">正在加载故事…</p>
</template>

<style scoped>
.workspace-loading {
  padding: 24px;
  color: var(--muted, #888);
}
</style>
