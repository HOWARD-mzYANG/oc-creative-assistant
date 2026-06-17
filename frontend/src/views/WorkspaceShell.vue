<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useProjectStore } from '../stores/useProjectStore'
import { useGraphStore } from '../stores/useGraphStore'
import { useChatStore } from '../stores/useChatStore'
import { usePanelResize } from '../composables/usePanelResize'
import { provideWorkspaceChatContext } from '../composables/useWorkspaceChatContext'
import WorkspaceSidebar from '../components/workspace/WorkspaceSidebar.vue'
import RightStageOutput from '../components/workspace/RightStageOutput.vue'
import BottomComposer from '../components/workspace/BottomComposer.vue'
import PanelToggleButton from '../components/workspace/PanelToggleButton.vue'

/**
 * 工作区外壳：左右面板可调整大小、可折叠，无顶部工具栏。
 */
const props = defineProps<{ projectId: string }>()

const projectStore = useProjectStore()
const graphStore = useGraphStore()
const chatStore = useChatStore()
const { triggerGraphRefresh } = provideWorkspaceChatContext()

const LEFT_MIN = 200
const LEFT_MAX = 460
const LEFT_DEFAULT = 280
const RIGHT_MIN = 280
const RIGHT_MAX = 760
const RIGHT_DEFAULT = 440
const COLLAPSED_WIDTH = 36

const leftOpen = ref(true)
const rightOpen = ref(true)
const leftWidth = ref(LEFT_DEFAULT)
const rightWidth = ref(RIGHT_DEFAULT)

const leftPanelWidth = computed(() => (leftOpen.value ? leftWidth.value : COLLAPSED_WIDTH))
const rightPanelWidth = computed(() => (rightOpen.value ? rightWidth.value : COLLAPSED_WIDTH))

const leftResize = usePanelResize({
  min: LEFT_MIN,
  max: LEFT_MAX,
  direction: 1,
  getWidth: () => leftWidth.value,
  setWidth: (w) => {
    leftWidth.value = w
  },
})

const rightResize = usePanelResize({
  min: RIGHT_MIN,
  max: RIGHT_MAX,
  direction: -1,
  getWidth: () => rightWidth.value,
  setWidth: (w) => {
    rightWidth.value = w
  },
})

const isResizing = computed(() => leftResize.isDragging.value || rightResize.isDragging.value)

async function refreshProjectGraphs() {
  await triggerGraphRefresh()
  const graphIds = [
    projectStore.plotGraphId,
    projectStore.characterGraphId,
    projectStore.worldGraphId,
  ].filter((id): id is string => Boolean(id))
  await Promise.all(graphIds.map((id) => graphStore.load(id, true)))
  await projectStore.loadProject(props.projectId, true)
}

onMounted(() => {
  void projectStore.loadProject(props.projectId)
  void chatStore.init(props.projectId)
  chatStore.setGraphMutatedHandler(refreshProjectGraphs)
})

watch(
  () => props.projectId,
  (id) => {
    void projectStore.loadProject(id)
    void chatStore.init(id)
  },
)

onBeforeUnmount(() => {
  chatStore.setGraphMutatedHandler(null)
})
</script>

<template>
  <div class="workspace-shell">
    <main class="workspace-shell__body" :class="{ 'is-resizing': isResizing }">
      <!-- 左侧面板 -->
      <aside
        class="side-panel side-panel--left"
        :class="{ 'is-collapsed': !leftOpen }"
        :style="{ width: `${leftPanelWidth}px` }"
      >
        <template v-if="leftOpen">
          <div class="side-panel__content">
            <WorkspaceSidebar :project-id="projectId" @collapse="leftOpen = false" />
          </div>
          <div
            class="resize-handle resize-handle--right"
            :class="{ 'is-dragging': leftResize.isDragging.value }"
            title="拖动调整大小"
            @mousedown="leftResize.startDrag"
          />
        </template>
        <div v-else class="side-panel__collapsed">
          <PanelToggleButton
            direction="left"
            :expanded="false"
            label="展开导航"
            @click="leftOpen = true"
          />
        </div>
      </aside>

      <!-- 中央区域 -->
      <div class="workspace-shell__center">
        <section class="workspace-shell__view">
          <router-view />
        </section>
        <BottomComposer />
      </div>

      <!-- 右侧面板 -->
      <aside
        class="side-panel side-panel--right"
        :class="{ 'is-collapsed': !rightOpen }"
        :style="{ width: `${rightPanelWidth}px` }"
      >
        <template v-if="rightOpen">
          <div
            class="resize-handle resize-handle--left"
            :class="{ 'is-dragging': rightResize.isDragging.value }"
            title="拖动调整大小"
            @mousedown="rightResize.startDrag"
          />
          <div class="side-panel__content">
            <RightStageOutput @collapse="rightOpen = false" />
          </div>
        </template>
        <div v-else class="side-panel__collapsed">
          <PanelToggleButton
            direction="right"
            :expanded="false"
            label="展开 AI 输出"
            @click="rightOpen = true"
          />
        </div>
      </aside>
    </main>

  </div>
</template>

<style scoped>
.workspace-shell {
  height: 100vh;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  background: var(--app-bg);
  color: var(--text);
  overflow: hidden;
}

.workspace-shell__body {
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.workspace-shell__body.is-resizing .side-panel {
  transition: none;
}

.workspace-shell__center {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
}

.workspace-shell__view {
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.workspace-shell__view > * {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.side-panel {
  position: relative;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: var(--panel);
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.side-panel--left {
  border-right: 1px solid var(--border);
}

.side-panel--right {
  border-left: 1px solid var(--border);
}

.side-panel__content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.side-panel__content :deep(.workspace-sidebar),
.side-panel__content :deep(.right-stage) {
  flex: 1;
  min-height: 0;
  border: none;
}

.side-panel__collapsed {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  background:
    radial-gradient(circle at 50% 0%, rgba(167, 139, 250, 0.1), transparent 65%),
    var(--panel);
}

.resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 6px;
  z-index: 5;
  cursor: col-resize;
  touch-action: none;
}

.resize-handle::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 2px;
  height: 32px;
  transform: translateY(-50%);
  border-radius: 2px;
  background: transparent;
  transition: background 0.15s ease;
}

.resize-handle--right {
  right: -3px;
}

.resize-handle--right::after {
  right: 2px;
}

.resize-handle--left {
  left: -3px;
}

.resize-handle--left::after {
  left: 2px;
}

.resize-handle:hover::after,
.resize-handle.is-dragging::after {
  background: var(--accent, #8b5cf6);
}

.resize-handle:hover,
.resize-handle.is-dragging {
  background: linear-gradient(
    to right,
    transparent,
    var(--accent-soft, rgba(139, 92, 246, 0.12)),
    transparent
  );
}
</style>
