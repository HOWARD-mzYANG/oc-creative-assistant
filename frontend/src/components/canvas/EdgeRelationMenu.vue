<script setup lang="ts">
import { RELATION_TYPE_OPTIONS, type CreativeRelationType } from '../../types/node'
import { getRelationStyle } from '../../utils/canvasRelations'

defineProps<{
  show: boolean
  x: number
  y: number
  currentType: CreativeRelationType
}>()

const emit = defineEmits<{
  select: [relationType: CreativeRelationType]
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="edge-relation-menu"
      :style="{ left: `${x}px`, top: `${y}px` }"
      @contextmenu.prevent
    >
      <p class="edge-relation-menu__title">关系类型</p>
      <button
        v-for="option in RELATION_TYPE_OPTIONS"
        :key="option.value"
        type="button"
        class="edge-relation-menu__item"
        :class="{ 'is-selected': currentType === option.value }"
        @click="emit('select', option.value)"
      >
        <span
          class="edge-relation-menu__swatch"
          :style="{ background: getRelationStyle(option.value).color }"
        />
        {{ option.label }}
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.edge-relation-menu {
  position: fixed;
  z-index: 9999;
  min-width: 180px;
  padding: 6px;
  background: #fff;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.edge-relation-menu__title {
  margin: 0;
  padding: 6px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted, #888);
}

.edge-relation-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: none;
  border-radius: 7px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #333);
}

.edge-relation-menu__item:hover {
  background: var(--accent-soft, rgba(124, 92, 255, 0.1));
}

.edge-relation-menu__item.is-selected {
  background: var(--accent-soft, rgba(124, 92, 255, 0.12));
  color: var(--accent-deep, #6743ff);
}

.edge-relation-menu__swatch {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex-shrink: 0;
}
</style>
