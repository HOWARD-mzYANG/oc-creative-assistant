<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useProjectStore } from '../../stores/useProjectStore'
import SubgraphCanvas from '../../components/workspace/SubgraphCanvas.vue'

/**
 * 故事 view (first_revision stage 3): a Vue Flow canvas bound to the plot sub-graph.
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
