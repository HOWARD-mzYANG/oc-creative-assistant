<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core'
import type { CreativeNodeData } from '../../types/node'
import NodeHandles from './NodeHandles.vue'

/**
 * 资料节点卡片。
 *
 * 资料节点是前端预留的 RAG 能力入口；目前只保存摘要和来源备注，不会直接触发检索。
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
