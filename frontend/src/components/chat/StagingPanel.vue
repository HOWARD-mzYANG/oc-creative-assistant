<script setup lang="ts">
import type { AgentStagingBatchDto } from '../../api/chatApi'
import StagingItemCard from './StagingItemCard.vue'

/**
 * 暂存批次列表。
 *
 * 同一轮智能体生成的变更会合并成一个批次，提供“全部接受”和“全部拒绝”快捷操作；
 * 同时也支持逐条处理。
 */
defineProps<{
  batches: AgentStagingBatchDto[]
}>()

const emit = defineEmits<{
  resolveItem: [stagingId: string, action: 'accept' | 'reject']
  resolveBatch: [batchId: string, action: 'accept_all' | 'reject_all']
}>()
</script>

<template>
  <section v-if="batches.length > 0" class="staging-panel">
    <header class="staging-panel__head">
      <h3>待处理变更</h3>
      <span class="staging-panel__count">{{ batches.length }} 个批次</span>
    </header>

    <div v-for="batch in batches" :key="batch.batch_id" class="staging-batch">
      <header class="staging-batch__head">
        <span>本批次 {{ batch.items.length }} 项</span>
        <div class="staging-batch__actions">
          <button type="button" @click="emit('resolveBatch', batch.batch_id, 'accept_all')">
            全部接受
          </button>
          <button type="button" class="ghost" @click="emit('resolveBatch', batch.batch_id, 'reject_all')">
            全部拒绝
          </button>
        </div>
      </header>
      <div class="staging-batch__items">
        <StagingItemCard
          v-for="item in batch.items"
          :key="item.id"
          :item="item"
          @resolve="(id, action) => emit('resolveItem', id, action)"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.staging-panel {
  display: grid;
  gap: 10px;
}

.staging-panel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.staging-panel__head h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text);
}

.staging-panel__count {
  font-size: 0.78rem;
  color: var(--muted);
}

.staging-batch {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--app-bg);
}

.staging-batch__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.78rem;
  color: var(--muted);
}

.staging-batch__actions {
  display: flex;
  gap: 6px;
}

.staging-batch__actions button {
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.78rem;
  cursor: pointer;
}

.staging-batch__actions .ghost {
  color: var(--muted);
  background: #ffffff;
  border-color: var(--border);
}

.staging-batch__items {
  display: grid;
  gap: 8px;
}
</style>
