<script setup lang="ts">
import type { CreativeNodeType } from '../../types/node'

/**
 * Canvas right-click context menu.
 *
 * menuType='blank': create a new node at the cursor position (using the types allowed by the current sub-graph).
 * menuType='node': edit details / duplicate / delete / copy to composer.
 * position:fixed + z-index:9999, sits above nodes and the canvas.
 */
defineProps<{
  show: boolean
  x: number
  y: number
  menuType: 'blank' | 'node' | 'edge'
  createTypes: CreativeNodeType[]
  edgeLabel?: string
}>()
const emit = defineEmits<{
  create: [type: CreativeNodeType]
  edit: []
  duplicate: []
  remove: []
  quote: []
  changeRelation: []
  close: []
}>()

function labelOf(type: CreativeNodeType): string {
  return ({character:'角色',worldbuilding:'世界观',plot:'故事节点',idea:'想法',research:'资料',structure:'结构'} as Record<string,string>)[type] ?? type
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="ctx-menu" :style="{ left: `${x}px`, top: `${y}px` }" @contextmenu.prevent>
      <template v-if="menuType === 'blank'">
        <button
          v-for="type in createTypes"
          :key="type"
          type="button"
          class="ctx-menu__item"
          @click="emit('create', type)"
        >
          + 新建{{ labelOf(type) }}
        </button>
      </template>
      <template v-else-if="menuType === 'edge'">
        <p v-if="edgeLabel" class="ctx-menu__caption">{{ edgeLabel }}</p>
        <button type="button" class="ctx-menu__item" @click="emit('changeRelation')">更改关系</button>
        <button type="button" class="ctx-menu__item ctx-menu__item--danger" @click="emit('remove')">
          删除边
        </button>
      </template>
      <template v-else>
        <button type="button" class="ctx-menu__item" @click="emit('edit')">编辑</button>
        <button type="button" class="ctx-menu__item" @click="emit('duplicate')">复制</button>
        <button type="button" class="ctx-menu__item" @click="emit('quote')">复制到输入框</button>
        <button type="button" class="ctx-menu__item ctx-menu__item--danger" @click="emit('remove')">
          删除
        </button>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-menu {
  position: fixed;
  z-index: 9999;
  min-width: 140px;
  padding: 4px;
  background: #fff;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  display: flex;
  flex-direction: column;
}
.ctx-menu__caption {
  margin: 0;
  padding: 6px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted, #888);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.ctx-menu__item {
  text-align: left;
  padding: 8px 12px;
  border: none;
  background: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text, #333);
}
.ctx-menu__item:hover {
  background: #f3f4f6;
}
.ctx-menu__item--danger {
  color: #dc2626;
}
</style>
