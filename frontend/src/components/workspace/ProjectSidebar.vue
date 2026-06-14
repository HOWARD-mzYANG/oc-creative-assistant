<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  loadRagContext,
  searchProjectMemory,
  type IndexingStatusDto,
  type MemorySearchItemDto,
  type RagMergedContextItemDto,
} from '../../api/graphApi'
import type { CreativeFlowNode, CreativeNodeType } from '../../types/node'
import { nodeTypeOptions } from '../../utils/nodeFactory'

/**
 * Left-hand project sidebar.
 *
 * Displays the node types that can be created, project-memory navigation, and a
 * lightweight search entry point; graph writes are still handled centrally by
 * AppShell, while the sidebar only emits create and select intents.
 */
const props = defineProps<{
  projectId: string
  nodes: CreativeFlowNode[]
  selectedNode: CreativeFlowNode | null
  indexingStatus?: IndexingStatusDto
}>()

const emit = defineEmits<{
  createNode: [nodeType: CreativeNodeType]
  nodeSelected: [nodeId: string]
}>()

type MemoryFilterType = CreativeNodeType | 'all'

const memorySearchQuery = ref('')
const memorySearchType = ref<MemoryFilterType>('all')
const memorySearchItems = ref<MemorySearchItemDto[]>([])
const memorySearchError = ref('')
const isMemorySearching = ref(false)
const isMemorySearchTypeSelectOpen = ref(false)
const relatedMemoryItems = ref<RagMergedContextItemDto[]>([])
const relatedMemoryError = ref('')
const isRelatedMemoryLoading = ref(false)

function closeAllSelects(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.custom-select-container')) {
    isMemorySearchTypeSelectOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeAllSelects)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAllSelects)
})


const memoryGroups = computed(() =>
  nodeTypeOptions
    .map((option) => ({
      ...option,
      nodes: props.nodes.filter((node) => node.data.nodeType === option.type),
    }))
    .filter((group) => group.nodes.length > 0),
)


/**
 * Truncate the node body so long settings don't crowd the left-hand memory list.
 *
 * Args:
 *   content: The node's full body text.
 *
 * Returns:
 *   A short summary for the card preview.
 */
function summarizeContent(content: string) {
  if (!content.trim()) {
    return '暂无内容'
  }

  return content.length > 72 ? `${content.slice(0, 72)}...` : content
}

function getNodeTypeLabel(type: string) {
  return nodeTypeOptions.find((option) => option.type === type)?.label ?? type
}

function getMemorySourceLabel(source: string) {
  if (source === 'both') {
    return '图关系 + 语义'
  }

  return source === 'graph' ? '图关系' : '语义匹配'
}

/**
 * Request creation of a node of the given type.
 *
 * Args:
 *   nodeType: The node type the user selected in the left toolbar.
 */
function handleCreateNode(nodeType: CreativeNodeType) {
  emit('createNode', nodeType)
}

function handleSelectNode(nodeId: string) {
  emit('nodeSelected', nodeId)
}

/**
 * Load related memories for the currently selected node.
 *
 * The left panel only shows the merged, concise memory cards; the full prompt and
 * vector debug info remain in the right-hand panel.
 */
async function handleLoadRelatedMemory() {
  if (!props.selectedNode) {
    return
  }

  try {
    isRelatedMemoryLoading.value = true
    relatedMemoryError.value = ''
    const result = await loadRagContext({
      node_id: props.selectedNode.id,
      query: '',
      agent_type: 'inspiration',
      top_k: 5,
    })

    relatedMemoryItems.value = result.merged_context
  } catch (error) {
    relatedMemoryItems.value = []
    relatedMemoryError.value = error instanceof Error ? error.message : '相关记忆加载失败'
  } finally {
    isRelatedMemoryLoading.value = false
  }
}

/**
 * Run a semantic search across project-level memory.
 *
 * This entry point does not depend on the current node, so it suits searching
 * existing lore directly by question; indexing errors only show a short hint.
 */
async function handleSearchMemory() {
  const query = memorySearchQuery.value.trim()

  if (!props.projectId || !query) {
    memorySearchError.value = '请输入要搜索的记忆问题'
    return
  }

  try {
    isMemorySearching.value = true
    memorySearchError.value = ''
    const result = await searchProjectMemory(props.projectId, {
      query,
      node_type: memorySearchType.value === 'all' ? null : memorySearchType.value,
      top_k: 6,
    })

    memorySearchItems.value = result.items
    if (result.debug.vector_error) {
      memorySearchError.value = result.debug.vector_error
    }
  } catch (error) {
    memorySearchItems.value = []
    memorySearchError.value = error instanceof Error ? error.message : '记忆搜索失败'
  } finally {
    isMemorySearching.value = false
  }
}

watch(
  () => props.selectedNode?.id,
  () => {
    relatedMemoryItems.value = []
    relatedMemoryError.value = ''
  },
)
</script>

<template>
  <!-- Left sidebar: node types, project-memory navigation, and a lightweight search entry point -->
  <aside class="project-sidebar">
    <section class="sidebar-section">
      <h2>节点类型</h2>
      <div class="node-type-list">
        <button
          v-for="option in nodeTypeOptions"
          :key="option.type"
          type="button"
          class="node-type-button"
          @click="handleCreateNode(option.type)"
        >
          <span class="node-icon">{{ option.icon }}</span>
          <span>
            <strong>{{ option.label }}</strong>
            <small>{{ option.description }}</small>
          </span>
        </button>
      </div>
    </section>

    <!-- <section class="sidebar-section"> -->
      <!-- <div class="section-header">
        <h2>Lore Memory</h2>
        <span class="memory-health" :class="memoryHealth.tone">{{ memoryHealth.label }}</span>
      </div>
      <div class="memory-stats">
        <article v-for="stat in memoryStats" :key="stat.type" class="memory-stat">
          <span>{{ stat.icon }}</span>
          <strong>{{ stat.count }}</strong>
          <small>{{ stat.label }}</small>
        </article>
      </div> -->
    <!-- </section> -->

    <section class="sidebar-section">
      <h2>记忆列表</h2>
      <p v-if="memoryGroups.length === 0" class="empty-copy">还没有节点，请先从上方创建一条创意记忆。</p>
      <details v-for="group in memoryGroups" :key="group.type" class="memory-group" open>
        <summary>
          <span>{{ group.icon }} {{ group.label }}</span>
          <small>{{ group.nodes.length }}</small>
        </summary>
        <button
          v-for="node in group.nodes"
          :key="node.id"
          type="button"
          class="memory-card"
          :class="{ 'is-active': selectedNode?.id === node.id }"
          @click="handleSelectNode(node.id)"
        >
          <strong>{{ node.data.title }}</strong>
          <span>{{ node.data.status }} · {{ node.data.tags.join(' / ') || '无标签' }}</span>
          <p>{{ summarizeContent(node.data.content) }}</p>
        </button>
      </details>
    </section>

    <section class="sidebar-section">
      <h2>相关记忆</h2>
      <template v-if="selectedNode">
        <p class="context-copy">查看图关系以及语义相近的记忆：“{{ selectedNode.data.title }}”。</p>
        <button type="button" class="secondary-button" :disabled="isRelatedMemoryLoading" @click="handleLoadRelatedMemory">
          {{ isRelatedMemoryLoading ? '加载中…' : '查看相关记忆' }}
        </button>
        <p v-if="relatedMemoryError" class="memory-error">{{ relatedMemoryError }}</p>
        <p v-else-if="relatedMemoryItems.length === 0" class="empty-copy">点击按钮显示与当前节点相关的记忆。</p>
        <button
          v-for="item in relatedMemoryItems"
          :key="item.id"
          type="button"
          class="memory-card compact"
          @click="handleSelectNode(item.id)"
        >
          <strong>{{ item.title }}</strong>
          <span>{{ getMemorySourceLabel(item.source) }} · {{ getNodeTypeLabel(item.type) }}</span>
          <p>{{ summarizeContent(item.content) }}</p>
        </button>
      </template>
      <p v-else class="empty-copy">选择一个节点，在这里查看相关记忆。</p>
    </section>

    <section class="sidebar-section">
      <h2>项目记忆搜索</h2>
      <div class="memory-search">
        <input
          v-model="memorySearchQuery"
          type="text"
          placeholder="例如：谁和涩谷站线有关？"
          @keydown.enter.prevent="handleSearchMemory"
        />
        <div class="custom-select-container">
          <div
            class="custom-select-trigger"
            :class="{ 'is-open': isMemorySearchTypeSelectOpen }"
            @click="isMemorySearchTypeSelectOpen = !isMemorySearchTypeSelectOpen"
          >
            <span>{{ memorySearchType === 'all' ? '全部类型' : (nodeTypeOptions.find(opt => opt.type === memorySearchType)?.label || memorySearchType) }}</span>
            <div class="custom-select-arrow"></div>
          </div>
          <ul class="custom-select-options" v-show="isMemorySearchTypeSelectOpen">
            <li
              class="custom-select-option"
              :class="{ 'is-selected': memorySearchType === 'all' }"
              @click="memorySearchType = 'all'; isMemorySearchTypeSelectOpen = false"
            >
              全部类型
            </li>
            <li
              v-for="option in nodeTypeOptions"
              :key="option.type"
              class="custom-select-option"
              :class="{ 'is-selected': memorySearchType === option.type }"
              @click="memorySearchType = option.type; isMemorySearchTypeSelectOpen = false"
            >
              {{ option.label }}
            </li>
          </ul>
        </div>
        <button type="button" :disabled="isMemorySearching" @click="handleSearchMemory">
          {{ isMemorySearching ? '搜索中…' : '搜索记忆' }}
        </button>
      </div>
      <p v-if="memorySearchError" class="memory-error">{{ memorySearchError }}</p>
      <p v-else-if="memorySearchItems.length === 0" class="empty-copy">输入问题，在当前项目的既有设定中搜索。</p>
      <button
        v-for="item in memorySearchItems"
        :key="item.id"
        type="button"
        class="memory-card compact"
        @click="handleSelectNode(item.id)"
      >
        <strong>{{ item.title }}</strong>
        <span>分数 {{ item.score.toFixed(2) }} · {{ getNodeTypeLabel(item.type) }}</span>
        <p>{{ summarizeContent(item.content) }}</p>
      </button>
    </section>
  </aside>
</template>

<style scoped src="./ProjectSidebar.scoped.css"></style>
