<script setup lang="ts">
import type { WorkspaceStatus } from '../../types/workspace'

/**
 * 底部状态栏。
 *
 * 只展示 AppShell 聚合后的保存、索引和模型状态；
 * 不直接触发保存、索引构建或模型调用。
 */
defineProps<{
  status: WorkspaceStatus
}>()
</script>

<template>
  <!-- 状态栏：展示保存、索引和模型状态。 -->
  <footer class="status-bar">
    <div class="status-left">
      <span class="status-item save-status">
        <span class="status-dot" :class="{ 'is-saving': status.saveState.includes('保存中') || status.saveState.includes('Saving') }"></span>
        {{ status.saveState }}
      </span>
    </div>
    <div class="status-right">
      <span class="status-item">{{ status.indexState }}</span>
      <span class="status-item">{{ status.modelState }}</span>
    </div>
  </footer>
</template>

<style scoped>
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 16px;
  background: var(--panel-strong);
  color: var(--muted);
  font-size: 0.78rem;
}

.status-left,
.status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981; /* 默认绿色：已保存 / 就绪。 */
  transition: all 0.3s ease;
}

.status-dot.is-saving {
  background: #f59e0b; /* 琥珀色：正在保存。 */
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.2);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (max-width: 640px) {
  .status-bar {
    flex-direction: column;
    align-items: stretch;
    padding: 8px 12px;
    gap: 8px;
  }

  .status-left,
  .status-right {
    justify-content: space-between;
  }
}
</style>
