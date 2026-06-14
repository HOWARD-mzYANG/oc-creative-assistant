<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core'
import type { CreativeNodeData } from '../../types/node'
import NodeHandles from './NodeHandles.vue'

/**
 * 结构 node card.
 *
 * 结构 nodes organize multiple materials into character sheets, relationship summaries, or plot frameworks; for now they only handle canvas display.
 */
defineProps<NodeProps<CreativeNodeData>>()
</script>

<template>
  <article class="creative-node structure" :class="{ selected: selected || data.isActive }">
    <NodeHandles :connectable="connectable" />
    <p class="node-type"><span>{{ data.icon }}</span>{{ data.typeLabel }}</p>
    <h3>{{ data.title }}</h3>
    <p class="node-summary">{{ data.content }}</p>
  </article>
</template>
