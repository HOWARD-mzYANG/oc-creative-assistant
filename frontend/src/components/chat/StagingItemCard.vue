<script setup lang="ts">
import { computed } from 'vue'
import type { AgentStagingItemDto } from '../../api/chatApi'

/**
 * Single staging item card.
 *
 * Shows a canvas change proposed by the Agent; the user chooses accept / reject to advance the state machine.
 * The payload rendering logic only covers create_node, the most common type, and falls back to JSON for other types.
 */
const props = defineProps<{
  item: AgentStagingItemDto
}>()

const emit = defineEmits<{
  resolve: [stagingId: string, action: 'accept' | 'reject']
}>()

const CHANGE_TYPE_LABELS: Record<string, string> = {
  create_node: '新建节点',
  create_edge: '新建关系',
  update_node: '更新节点',
  delete_node: '删除节点',
  delete_edge: '删除关系',
}
const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  accepted: '已接受',
  rejected: '已拒绝',
  edited: '已编辑',
}

const titleHint = computed(() => {
  const type = props.item.change_type
  if (type === 'create_node') {
    const payload = props.item.payload as { title?: string; node_type?: string; parent_id?: string; parentId?: string }
    const title = payload.title ?? '未命名节点'
    const parentId = payload.parent_id ?? payload.parentId
    const typeText = payload.node_type ? `${title} · ${payload.node_type}` : title
    return parentId ? `${typeText} · 子笔记` : typeText
  }
  return CHANGE_TYPE_LABELS[type] ?? type
})

const contentPreview = computed(() => {
  const item = props.item
  const payload = (item.payload ?? {}) as Record<string, unknown>

  if (item.change_type === 'create_node') {
    const lines = [(payload.content as string | undefined) ?? '']
    const parentId = (payload.parent_id as string | undefined) ?? (payload.parentId as string | undefined)
    const sortOrder = (payload.sort_order as number | string | undefined) ?? (payload.sortOrder as number | string | undefined)
    if (parentId) lines.push(`父笔记 ID：${parentId}`)
    if (sortOrder !== undefined) lines.push(`排序：${sortOrder}`)
    return lines.filter(Boolean).join('\n')
  }

  if (item.change_type === 'create_edge') {
    const source = (payload.source as string | undefined) ?? '?'
    const target = (payload.target as string | undefined) ?? '?'
    const relation = (payload.relation_type as string | undefined) ?? 'related'
    return `${source}  →  ${target}\n关系：${relation}`
  }

  if (item.change_type === 'update_node') {
    const fields = ['title', 'content', 'node_type', 'parent_id', 'parentId', 'sort_order', 'sortOrder']
      .filter((key) => payload[key] !== undefined)
      .map((key) => `${key}: ${payload[key]}`)
    return fields.join('\n')
  }

  if (item.change_type === 'delete_node') {
    return item.target_id ? `目标节点 ID：${item.target_id}` : ''
  }

  if (item.change_type === 'delete_edge') {
    if (item.target_id) {
      return `目标关系 ID：${item.target_id}`
    }
    const source = (payload.source as string | undefined) ?? '?'
    const target = (payload.target as string | undefined) ?? '?'
    return `${source}  →  ${target}`
  }

  return ''
})

const isPending = computed(() => props.item.status === 'pending')
</script>

<template>
  <article class="staging-item" :class="item.status">
    <header class="staging-item__head">
      <span class="staging-item__type">{{ item.change_type }}</span>
      <span class="staging-item__status">{{ STATUS_LABELS[item.status] ?? item.status }}</span>
    </header>
    <h4 class="staging-item__title">{{ titleHint }}</h4>
    <p v-if="contentPreview" class="staging-item__content">{{ contentPreview }}</p>
    <p v-if="item.reasoning" class="staging-item__reason">{{ item.reasoning }}</p>

    <footer v-if="isPending" class="staging-item__actions">
      <button type="button" class="accept" @click="emit('resolve', item.id, 'accept')">
        接受
      </button>
      <button type="button" class="reject" @click="emit('resolve', item.id, 'reject')">
        拒绝
      </button>
    </footer>
  </article>
</template>

<style scoped>
.staging-item {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
}

.staging-item.accepted {
  background: #f0fdfa;
  border-color: #ccfbf1;
}

.staging-item.rejected {
  background: #f9fafb;
  border-color: #e5e7eb;
  opacity: 0.7;
}

.staging-item__head {
  display: flex;
  justify-content: space-between;
  font-size: 0.74rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.staging-item__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text);
}

.staging-item__content {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.staging-item__reason {
  margin: 0;
  padding-top: 6px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  font-size: 0.78rem;
  color: var(--muted);
}

.staging-item__actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.staging-item__actions button {
  flex: 1;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.84rem;
  font-weight: 500;
  cursor: pointer;
}

.staging-item__actions .accept {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}

.staging-item__actions .accept:hover {
  background: #d1fae5;
}

.staging-item__actions .reject {
  color: #b91c1c;
  border-color: #fecaca;
  background: #fef2f2;
}

.staging-item__actions .reject:hover {
  background: #fee2e2;
}
</style>
