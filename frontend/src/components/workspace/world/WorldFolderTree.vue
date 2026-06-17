<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WorldMoveTarget, WorldTreeNode } from '../../../utils/worldHierarchy'

const props = defineProps<{
  forest: WorldTreeNode[]
  selectedId: string
}>()

const emit = defineEmits<{
  select: [id: string]
  'add-child': [parentId: string]
  'add-root': []
  delete: [id: string]
  move: [draggedId: string, target: WorldMoveTarget]
}>()

const collapsed = ref<Set<string>>(new Set())
const draggedId = ref<string | null>(null)
const dragReadyId = ref<string | null>(null)
const dropHint = ref<{ id: string; mode: 'child' | 'before' } | 'root' | null>(null)

interface FlatRow {
  id: string
  title: string
  depth: number
  hasChildren: boolean
  isCollapsed: boolean
}

function flatten(tree: WorldTreeNode, depth: number, rows: FlatRow[]) {
  rows.push({
    id: tree.id,
    title: tree.node.data.title || '未命名',
    depth,
    hasChildren: tree.children.length > 0,
    isCollapsed: collapsed.value.has(tree.id),
  })
  if (collapsed.value.has(tree.id)) return
  for (const child of tree.children) {
    flatten(child, depth + 1, rows)
  }
}

const rows = computed(() => {
  const list: FlatRow[] = []
  for (const root of props.forest) {
    flatten(root, 0, list)
  }
  return list
})

function toggleCollapse(id: string, event: MouseEvent) {
  event.stopPropagation()
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}

function onHandlePointerDown(id: string) {
  dragReadyId.value = id
}

function onDragStart(id: string, event: DragEvent) {
  if (dragReadyId.value !== id) {
    event.preventDefault()
    return
  }
  draggedId.value = id
  dropHint.value = null
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    // Chromium / Electron 中需要设置数据，drop 事件才会触发。
    event.dataTransfer.setData('text/plain', id)
    event.dataTransfer.setData('application/x-world-node-id', id)
  }
}

function onDragEnd() {
  dragReadyId.value = null
  draggedId.value = null
  dropHint.value = null
}

function resolveDraggedId(event: DragEvent): string | null {
  const fromState = draggedId.value
  if (fromState) return fromState
  const fromTransfer =
    event.dataTransfer?.getData('application/x-world-node-id') ||
    event.dataTransfer?.getData('text/plain')
  return fromTransfer || null
}

function onListDragLeave(event: DragEvent) {
  const next = event.relatedTarget as Node | null
  const current = event.currentTarget as HTMLElement
  if (next && current.contains(next)) return
  dropHint.value = null
}

function resolveDropMode(event: DragEvent, rowElement: HTMLElement): 'child' | 'before' {
  const rect = rowElement.getBoundingClientRect()
  const relativeY = event.clientY - rect.top
  return relativeY < rect.height * 0.35 ? 'before' : 'child'
}

function onRowDragOver(id: string, event: DragEvent) {
  if (!draggedId.value || draggedId.value === id) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  const rowElement = event.currentTarget as HTMLElement
  dropHint.value = { id, mode: resolveDropMode(event, rowElement) }
}

function onRootDragOver(event: DragEvent) {
  if (!draggedId.value) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dropHint.value = 'root'
}

function onRowDrop(id: string, event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  const sourceId = resolveDraggedId(event)
  if (!sourceId || sourceId === id) {
    onDragEnd()
    return
  }
  const rowElement = event.currentTarget as HTMLElement
  const mode = resolveDropMode(event, rowElement)
  emit(
    'move',
    sourceId,
    mode === 'before' ? { type: 'before', siblingId: id } : { type: 'child', parentId: id },
  )
  onDragEnd()
}

function onRootDrop(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  const sourceId = resolveDraggedId(event)
  if (!sourceId) {
    onDragEnd()
    return
  }
  emit('move', sourceId, { type: 'root' })
  onDragEnd()
}

function rowDropClass(id: string) {
  if (!dropHint.value || dropHint.value === 'root') return null
  if (dropHint.value.id !== id) return null
  return dropHint.value.mode === 'child' ? 'is-drop-child' : 'is-drop-before'
}
</script>

<template>
  <div class="world-folder-tree">
    <h3 class="world-folder-tree__title">模块</h3>

    <nav
      class="world-folder-tree__list"
      aria-label="世界观笔记"
      @dragover.prevent
      @dragleave="onListDragLeave"
    >
      <div
        v-for="row in rows"
        :key="row.id"
        class="world-folder-tree__row"
        :class="[
          {
            'is-selected': selectedId === row.id,
            'is-dragging': draggedId === row.id,
          },
          rowDropClass(row.id),
        ]"
        :style="{ paddingLeft: `${12 + row.depth * 16}px` }"
        draggable="true"
        @dragstart="onDragStart(row.id, $event)"
        @dragend="onDragEnd"
        @dragover="onRowDragOver(row.id, $event)"
        @drop="onRowDrop(row.id, $event)"
      >
        <span
          class="world-folder-tree__drag"
          role="button"
          tabindex="0"
          aria-label="拖动以排序或调整层级"
          title="拖动以调整层级"
          @mousedown.stop="onHandlePointerDown(row.id)"
          @touchstart.stop="onHandlePointerDown(row.id)"
        >
          ⠿
        </span>
        <button
          type="button"
          class="world-folder-tree__remove"
          aria-label="删除笔记"
          title="删除笔记"
          @click.stop="emit('delete', row.id)"
        >
          −
        </button>
        <button type="button" class="world-folder-tree__main" @click="emit('select', row.id)">
          <span
            v-if="row.hasChildren"
            class="world-folder-tree__chevron"
            :class="{ 'is-collapsed': row.isCollapsed }"
            @click="toggleCollapse(row.id, $event)"
          />
          <span v-else class="world-folder-tree__chevron world-folder-tree__chevron--spacer" />
          <span class="world-folder-tree__icon">{{ row.depth === 0 ? '📁' : '📄' }}</span>
          <span class="world-folder-tree__label">{{ row.title }}</span>
        </button>
        <button
          type="button"
          class="world-folder-tree__add"
          aria-label="添加子笔记"
          title="添加子笔记"
          @click.stop="emit('add-child', row.id)"
        >
          +
        </button>
      </div>

      <div
        class="world-folder-tree__row world-folder-tree__row--root"
        :class="{ 'is-drop-root': dropHint === 'root' }"
        @dragover="onRootDragOver"
        @drop="onRootDrop"
      >
        <button type="button" class="world-folder-tree__main" @click="emit('add-root')">
          <span class="world-folder-tree__chevron world-folder-tree__chevron--spacer" />
          <span class="world-folder-tree__icon">📁</span>
          <span class="world-folder-tree__label world-folder-tree__label--muted">新建根笔记</span>
        </button>
        <button
          type="button"
          class="world-folder-tree__add"
          aria-label="添加根笔记"
          title="添加根笔记"
          @click.stop="emit('add-root')"
        >
          +
        </button>
      </div>
    </nav>

    <p class="world-folder-tree__hint">拖动 ⠿ 可放入文件夹、调整排序，或拖到“新建根笔记”。</p>
  </div>
</template>

<style scoped>
.world-folder-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.world-folder-tree__title {
  margin: 0;
  padding: 2px 4px 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.world-folder-tree__hint {
  margin: 0;
  padding: 0 4px;
  font-size: 10px;
  line-height: 1.45;
  color: var(--muted);
}

.world-folder-tree__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.world-folder-tree__row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 4px;
  border-radius: 8px;
  transition: background 0.12s ease, box-shadow 0.12s ease;
}

.world-folder-tree__row:hover {
  background: var(--accent-soft);
}

.world-folder-tree__row.is-selected {
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1.5px var(--accent-border);
}

.world-folder-tree__row.is-selected .world-folder-tree__main {
  color: var(--accent-deep);
}

.world-folder-tree__row.is-dragging {
  opacity: 0.45;
}

.world-folder-tree__row.is-drop-child {
  background: rgba(124, 92, 255, 0.14);
  box-shadow: inset 0 0 0 1.5px var(--accent-border);
}

.world-folder-tree__row.is-drop-before::before {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  top: 0;
  height: 2px;
  border-radius: 1px;
  background: var(--accent);
}

.world-folder-tree__row--root {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.world-folder-tree__row--root.is-drop-root {
  background: rgba(124, 92, 255, 0.1);
  box-shadow: inset 0 0 0 1.5px var(--accent-border);
}

.world-folder-tree__drag {
  flex-shrink: 0;
  width: 18px;
  height: 22px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  line-height: 1;
  cursor: grab;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease, background 0.12s ease;
}

.world-folder-tree__row:hover .world-folder-tree__drag,
.world-folder-tree__row.is-dragging .world-folder-tree__drag {
  opacity: 1;
}

.world-folder-tree__drag:active {
  cursor: grabbing;
}

.world-folder-tree__drag:hover {
  color: var(--accent-deep);
  background: rgba(124, 92, 255, 0.1);
}

.world-folder-tree__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 4px 8px 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.world-folder-tree__remove,
.world-folder-tree__add {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 15px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease, color 0.12s ease, background 0.12s ease;
}

.world-folder-tree__row:hover .world-folder-tree__remove,
.world-folder-tree__row:hover .world-folder-tree__add,
.world-folder-tree__row--root .world-folder-tree__add {
  opacity: 1;
}

.world-folder-tree__remove:hover {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.1);
}

.world-folder-tree__add:hover {
  color: var(--accent-deep);
  background: rgba(124, 92, 255, 0.12);
}

.world-folder-tree__chevron {
  width: 14px;
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted);
  transform: rotate(90deg);
  transition: transform 0.15s ease;
}

.world-folder-tree__chevron.is-collapsed {
  transform: rotate(0deg);
}

.world-folder-tree__chevron--spacer {
  visibility: hidden;
}

.world-folder-tree__icon {
  flex-shrink: 0;
  font-size: 13px;
}

.world-folder-tree__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.world-folder-tree__label--muted {
  color: var(--muted);
  font-weight: 500;
}
</style>
