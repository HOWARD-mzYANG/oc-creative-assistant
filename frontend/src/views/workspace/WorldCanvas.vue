<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useProjectStore } from '../../stores/useProjectStore'
import WorldNotesWorkspace from '../../components/workspace/world/WorldNotesWorkspace.vue'

/**
 * 世界观 view: folder notes by default, optional tree canvas derived from hierarchy.
 */
const { worldGraphId } = storeToRefs(useProjectStore())
</script>

<template>
  <WorldNotesWorkspace
    v-if="worldGraphId"
    :key="worldGraphId"
    :graph-id="worldGraphId"
  />
  <p v-else class="workspace-loading">正在加载世界观…</p>
</template>

<style scoped>
.workspace-loading {
  padding: 24px;
  color: var(--muted, #888);
}
</style>
