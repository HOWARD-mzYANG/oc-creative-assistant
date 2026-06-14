<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core'
import type { CreativeNodeData } from '../../types/node'
import NodeHandles from './NodeHandles.vue'

/**
 * 资料 node card.
 *
 * The research node is a frontend entry-point placeholder for RAG capabilities; for now it only stores a summary and source notes, without directly triggering retrieval.
 */
defineProps<NodeProps<CreativeNodeData>>()
</script>

<template>
  <article class="creative-node research" :class="{ selected: selected || data.isActive }">
    <NodeHandles :connectable="connectable" />
    <p class="node-type"><span>{{ data.icon }}</span>{{ data.typeLabel }}</p>
    <h3>{{ data.title }}</h3>
    <p class="node-summary">{{ data.content }}</p>
  </article>
</template>
