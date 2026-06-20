<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../../stores/useProjectStore'
import { useWorldViewStore } from '../../stores/useWorldViewStore'
import PanelToggleButton from './PanelToggleButton.vue'
import ProjectIoButtons from './ProjectIoButtons.vue'

/**
 * 工作区左侧导航（first_revision 第 3 阶段）。
 *
 * 从上到下依次是：返回项目库、项目名称 + 摘要、三视图导航（故事 / 角色 / 世界观）以及 seed 版本。
 * 导航使用 router-link，每个子视图按自己的 graph_id 加载。
 */
const props = defineProps<{ projectId: string }>()

defineEmits<{ collapse: [] }>()

const route = useRoute()
const projectStore = useProjectStore()
const worldViewStore = useWorldViewStore()
const { detail } = storeToRefs(projectStore)
const { mode: worldMode } = storeToRefs(worldViewStore)

interface NavItem {
  id: string
  to: string
  icon: string
  canvasIcon?: string
  label: string
}

const seedLabel = computed(() => {
  const seed = detail.value?.latest_seed
  if (!seed) return '项目种子尚未生成'
  const time = seed.created_at ? new Date(seed.created_at) : null
  const timeLabel = time && !Number.isNaN(time.getTime()) ? ` · ${time.toLocaleString()}` : ''
  return `项目种子 v${seed.version}${timeLabel}`
})

const navItems = computed<NavItem[]>(() => [
  { id: 'overview', to: `/workspace/${props.projectId}/overview`, icon: '◷', label: '概览' },
  {
    id: 'world',
    to: `/workspace/${props.projectId}/world`,
    icon: '◍',
    canvasIcon: '⊞',
    label: '世界观',
  },
  { id: 'plot', to: `/workspace/${props.projectId}/plot`, icon: '❧', label: '故事' },
  { id: 'characters', to: `/workspace/${props.projectId}/characters`, icon: '✦', label: '角色' },
])

/** 判断当前状态是否满足条件。 */
function isNavActive(item: NavItem) {
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

/** 说明 navIcon 的局部业务逻辑。 */
function navIcon(item: NavItem) {
  if (item.id === 'world' && isNavActive(item) && worldMode.value === 'canvas') {
    return item.canvasIcon ?? item.icon
  }
  return item.icon
}

/** 说明 worldModeLabel 的局部业务逻辑。 */
function worldModeLabel(item: NavItem) {
  if (item.id !== 'world' || !isNavActive(item)) return ''
  return worldMode.value === 'notes' ? '笔记' : '树'
}

/** 处理对应的用户交互或组件事件。 */
function handleNavClick(item: NavItem, event: MouseEvent) {
  if (item.id !== 'world' || !isNavActive(item)) return
  event.preventDefault()
  worldViewStore.toggleMode()
}
</script>

<template>
  <aside class="workspace-sidebar">
    <div class="workspace-sidebar__header">
      <router-link class="workspace-sidebar__back" to="/library">← 项目库</router-link>
      <PanelToggleButton
        direction="left"
        expanded
        label="收起导航"
        @click="$emit('collapse')"
      />
    </div>

    <div class="workspace-sidebar__meta">
      <h2 class="workspace-sidebar__name">{{ detail?.name ?? '加载中…' }}</h2>
      <p class="workspace-sidebar__desc">{{ detail?.description || '暂无描述。' }}</p>
    </div>

    <nav class="workspace-sidebar__nav">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="workspace-sidebar__link"
        :class="{
          'is-active': isNavActive(item),
          'is-world-canvas': item.id === 'world' && isNavActive(item) && worldMode === 'canvas',
        }"
        :title="item.id === 'world' && isNavActive(item) ? '再次点击切换视图' : undefined"
        @click="handleNavClick(item, $event)"
      >
        <span class="workspace-sidebar__icon">{{ navIcon(item) }}</span>
        <span class="workspace-sidebar__label">{{ item.label }}</span>
        <span v-if="worldModeLabel(item)" class="workspace-sidebar__mode-tag">
          {{ worldModeLabel(item) }}
        </span>
      </router-link>
    </nav>

    <div class="workspace-sidebar__footer">
      <ProjectIoButtons variant="sidebar" />
      <div class="workspace-sidebar__footer-divider" aria-hidden="true" />
      <div class="workspace-sidebar__seed">{{ seedLabel }}</div>
    </div>
  </aside>
</template>

<style scoped>
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 14px;
  border-right: 1px solid var(--border);
  background:
    radial-gradient(circle at 20% 0%, rgba(167, 139, 250, 0.1), transparent 60%),
    var(--panel);
  overflow: auto;
}
.workspace-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.workspace-sidebar__back {
  font-size: 13px;
  color: var(--muted);
  text-decoration: none;
  transition: color 0.15s;
}
.workspace-sidebar__back:hover {
  color: var(--accent);
}
.workspace-sidebar__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.workspace-sidebar__name {
  font-size: 16px;
  font-weight: 700;
}
.workspace-sidebar__desc {
  font-size: 12px;
  color: var(--muted, #888);
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.workspace-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.workspace-sidebar__link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 11px;
  text-decoration: none;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  transition: background 0.16s, color 0.16s, transform 0.16s, box-shadow 0.16s;
}
.workspace-sidebar__link:hover {
  background: var(--accent-soft);
  color: var(--accent-deep);
  transform: translateX(2px);
}
.workspace-sidebar__link.is-active {
  background: var(--accent-soft);
  color: var(--accent-deep);
  box-shadow: inset 0 0 0 1.5px var(--accent-border);
}
.workspace-sidebar__link.is-active:hover {
  background: rgba(124, 92, 255, 0.16);
  color: var(--accent-deep);
  transform: none;
}
.workspace-sidebar__link.is-world-canvas.is-active {
  background: rgba(233, 130, 74, 0.12);
  color: #c45c2a;
  box-shadow: inset 0 0 0 1.5px rgba(233, 130, 74, 0.45);
}
.workspace-sidebar__link.is-world-canvas.is-active:hover {
  background: rgba(233, 130, 74, 0.18);
  color: #b04f22;
}
.workspace-sidebar__label {
  flex: 1;
  min-width: 0;
}
.workspace-sidebar__icon {
  min-width: 20px;
  font-size: 16px;
  text-align: center;
}
.workspace-sidebar__mode-tag {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  background: rgba(124, 92, 255, 0.14);
  color: var(--accent-deep);
}
.workspace-sidebar__link.is-world-canvas .workspace-sidebar__mode-tag {
  background: rgba(233, 130, 74, 0.18);
  color: #c45c2a;
}
.workspace-sidebar__footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  width: 100%;
}

.workspace-sidebar__footer-divider {
  width: 100%;
  height: 1px;
  background: var(--border);
}

.workspace-sidebar__seed {
  width: 100%;
  font-size: 11px;
  line-height: 1.45;
  color: var(--muted, #aaa);
  text-align: center;
  padding: 0 4px 2px;
}
</style>
