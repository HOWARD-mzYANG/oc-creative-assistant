<script setup lang="ts">
import { inject } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import type { CreativeNodeData } from '../../types/node'
import NodeHandles from './NodeHandles.vue'
import InlineEditableText from '../canvas/InlineEditableText.vue'

/**
 * 角色 node card.
 *
 * Title and summary support inline edit; on save, the value is written back via
 * the updateNodeData provided by CanvasWorkspace and triggers auto-save, without switching to the right panel.
 */
const props = defineProps<NodeProps<CreativeNodeData>>()
const updateNodeData = inject<(id: string, patch: { title?: string; content?: string }) => void>(
  'updateNodeData',
)
</script>

<template>
  <article class="creative-node character" :class="{ selected: selected || data.isActive }">
    <NodeHandles :connectable="connectable" />
    <p class="node-type"><span>{{ data.icon }}</span>{{ data.typeLabel }}</p>
    <h3>
      <InlineEditableText
        :model-value="data.title"
        placeholder="未命名角色"
        @save="(v) => updateNodeData?.(props.id, { title: v })"
      />
    </h3>
    <p class="node-summary">
      <InlineEditableText
        :model-value="data.content"
        placeholder="添加简短摘要"
        multiline
        @save="(v) => updateNodeData?.(props.id, { content: v })"
      />
    </p>
  </article>
</template>
