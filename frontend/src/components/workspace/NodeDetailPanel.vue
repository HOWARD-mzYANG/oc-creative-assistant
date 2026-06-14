<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { loadRagContext, type RagContextResponseDto } from '../../api/graphApi'
import type { CreativeFlowNode, CreativeNodeData } from '../../types/node'

/**
 * Node detail panel.
 *
 * Hosts node field editing, the Agent mock placeholder, and the RAG debug view at
 * once; all three only make sense when "a single node is selected", so they are
 * merged into the same child component, and switching nodes clears the temporary
 * preview via watch(props.selectedNode.id).
 */
const props = defineProps<{
  selectedNode: CreativeFlowNode
}>()

const emit = defineEmits<{
  'node-updated': [node: CreativeFlowNode]
  'node-deleted': [nodeId: string]
}>()

const agentResult = ref('')
const ragQuery = ref('')
const ragResult = ref<RagContextResponseDto | null>(null)
const ragError = ref('')
const isRagLoading = ref(false)

/* The custom dropdown does not use a native select, so the component must track the
   open state itself and collapse on outside clicks. */
const isNodeStatusSelectOpen = ref(false)

function closeAllSelects(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.custom-select-container')) {
    isNodeStatusSelectOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeAllSelects)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAllSelects)
})

const selectedNodeTags = computed(() => props.selectedNode.data.tags.join(', '))
const STATUS_LABELS: Record<CreativeNodeData['status'], string> = {
  draft: '草稿',
  synced: '已同步',
  outdated: '需更新',
}
const NODE_STATUS_OPTIONS: CreativeNodeData['status'][] = ['draft', 'synced', 'outdated']

function updateNodeData(partial: Partial<CreativeNodeData>) {
  emit('node-updated', {
    ...props.selectedNode,
    data: {
      ...props.selectedNode.data,
      ...partial,
    },
  })
}

function updateNodeTags(rawValue: string) {
  const tags = rawValue
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
  updateNodeData({ tags })
}

function handleDeleteNode() {
  emit('node-deleted', props.selectedNode.id)
}

/**
 * Generate a placeholder Agent result.
 *
 * The current mock only confirms the sidebar interaction and result presentation;
 * it does not auto-write into the node body, preserving the product boundary where
 * the user manually adopts generated content.
 */
function runAgentMock(type: 'inspiration' | 'research' | 'structure') {
  if (type === 'inspiration') {
    agentResult.value = JSON.stringify(
      {
        type: 'inspiration',
        suggestions: [
          '这个角色最核心的欲望是什么？',
          '这个设定会和哪个已有世界观节点发生冲突？',
          '是否需要一个事件节点来解释它的背景？',
        ],
      },
      null,
      2,
    )
    return
  }

  if (type === 'research') {
    agentResult.value = JSON.stringify(
      {
        type: 'research',
        summary: '未来这里会显示 RAG 或资料检索结果。',
        status: 'RAG 尚未连接',
      },
      null,
      2,
    )
    return
  }

  agentResult.value = JSON.stringify(
    {
      type: 'structure',
      summary: '未来这里会把多个节点整理成角色卡、关系图或剧情框架。',
      status: '结构 Agent 尚未连接',
    },
    null,
    2,
  )
}

function summarizeContent(content: string) {
  return content.length > 120 ? `${content.slice(0, 120)}...` : content
}

/**
 * Load the RAG debug context for the current node.
 *
 * Only displays the graph relations, vector context, and final prompt retrieved by
 * the backend; it does not call the LLM, nor does it write results back into the
 * node content.
 */
async function handleLoadRagContext() {
  try {
    isRagLoading.value = true
    ragError.value = ''
    ragResult.value = await loadRagContext({
      node_id: props.selectedNode.id,
      query: ragQuery.value,
      agent_type: 'inspiration',
      top_k: 5,
    })
  } catch (error) {
    ragResult.value = null
    ragError.value = error instanceof Error ? error.message : 'RAG 上下文加载失败'
  } finally {
    isRagLoading.value = false
  }
}

/* Clear the temporary preview when switching nodes, so the previous node's Agent/RAG
   results aren't mistaken for the current context. */
watch(
  () => props.selectedNode.id,
  () => {
    agentResult.value = ''
    ragResult.value = null
    ragError.value = ''
  },
)
</script>

<template>
  <div class="node-detail-panel">
    <section class="detail-header">
      <p>当前节点</p>
      <h2>{{ selectedNode.data.icon }} {{ selectedNode.data.title }}</h2>
      <span class="status-badge" :class="selectedNode.data.status">{{ selectedNode.data.status }}</span>
    </section>

    <section class="detail-panel">
      <label for="node-type">节点类型</label>
      <div class="input-wrapper">
        <input id="node-type" type="text" :value="selectedNode.data.typeLabel" disabled />
      </div>

      <label for="node-title">节点标题</label>
      <div class="input-wrapper">
        <input
          id="node-title"
          type="text"
          :value="selectedNode.data.title"
          @input="updateNodeData({ title: ($event.target as HTMLInputElement).value })"
        />
      </div>

      <label for="node-content">节点正文</label>
      <div class="input-wrapper">
        <textarea
          id="node-content"
          rows="4"
          :value="selectedNode.data.content"
          @input="updateNodeData({ content: ($event.target as HTMLTextAreaElement).value })"
        />
      </div>

      <label for="node-tags">标签</label>
      <div class="input-wrapper">
        <input
          id="node-tags"
          type="text"
          :value="selectedNodeTags"
          placeholder="用逗号分隔，例如：主角，第一幕"
          @input="updateNodeTags(($event.target as HTMLInputElement).value)"
        />
      </div>

      <label for="node-status">状态</label>
      <div class="custom-select-container">
        <div
          class="custom-select-trigger"
          :class="{ 'is-open': isNodeStatusSelectOpen }"
          @click="isNodeStatusSelectOpen = !isNodeStatusSelectOpen"
        >
          <span>{{ STATUS_LABELS[selectedNode.data.status] }}</span>
          <div class="custom-select-arrow"></div>
        </div>
        <ul class="custom-select-options" v-show="isNodeStatusSelectOpen">
          <li
            v-for="status in NODE_STATUS_OPTIONS"
            :key="status"
            class="custom-select-option"
            :class="{ 'is-selected': selectedNode.data.status === status }"
            @click="updateNodeData({ status }); isNodeStatusSelectOpen = false"
          >
            {{ STATUS_LABELS[status] }}
          </li>
        </ul>
      </div>

      <button type="button" class="danger" @click="handleDeleteNode">删除节点</button>
    </section>

    <section class="detail-panel">
      <h3>Agent 操作占位</h3>
      <div class="agent-actions">
        <button type="button" @click="runAgentMock('inspiration')">灵感</button>
        <button type="button" @click="runAgentMock('research')">资料</button>
        <button type="button" @click="runAgentMock('structure')">结构</button>
      </div>
      <pre v-if="agentResult" class="agent-result">{{ agentResult }}</pre>
    </section>

    <section class="detail-panel rag-panel">
      <h3>RAG / Agent 调试</h3>
      <label for="rag-query">用户请求</label>
      <div class="input-wrapper">
        <textarea
          id="rag-query"
          rows="3"
          v-model="ragQuery"
          placeholder="留空则使用当前节点标题和正文作为检索问题"
        />
      </div>
      <!-- This button only inspects the context; it does not call the LLM, nor does it write results into the node body. -->
      <button type="button" :disabled="isRagLoading" @click="handleLoadRagContext">
        {{ isRagLoading ? '正在加载 RAG 上下文…' : '查看 RAG 上下文' }}
      </button>
      <p v-if="ragError" class="rag-error">{{ ragError }}</p>

      <div v-if="ragResult" class="rag-result">
        <details open>
          <summary>当前节点</summary>
          <div class="rag-card">
            <strong>{{ ragResult.current_node.title }}</strong>
            <span>{{ ragResult.current_node.type }}</span>
            <p>{{ ragResult.current_node.content }}</p>
          </div>
        </details>

        <details open>
          <summary>图关系上下文</summary>
          <p v-if="ragResult.graph_context.length === 0" class="rag-empty">暂无直接连接的相关节点</p>
          <article v-for="item in ragResult.graph_context" :key="item.id" class="rag-card">
            <strong>{{ item.relation_label }} / {{ item.relation_type }}</strong>
            <span>{{ item.direction }} · {{ item.type }} · {{ item.title }}</span>
            <p>{{ summarizeContent(item.content) }}</p>
          </article>
        </details>

        <details open>
          <summary>向量上下文</summary>
          <p v-if="ragResult.vector_context.length === 0" class="rag-empty">暂无向量检索结果</p>
          <article v-for="item in ragResult.vector_context" :key="item.id" class="rag-card">
            <strong>score {{ item.score.toFixed(2) }}</strong>
            <span>{{ item.type }} · {{ item.title }}</span>
            <p>{{ summarizeContent(item.content) }}</p>
          </article>
          <p class="rag-debug-line">
            vector_store: {{ ragResult.debug.vector_store }}
            <span v-if="ragResult.debug.vector_error"> / {{ ragResult.debug.vector_error }}</span>
          </p>
        </details>

        <details>
          <summary>最终 Prompt</summary>
          <!-- Show the user the context the AI will receive first, to help verify that retrieval and assembly are reasonable. -->
          <pre class="prompt-preview">{{ ragResult.prompt }}</pre>
        </details>
      </div>
    </section>
  </div>
</template>

<style scoped src="./AgentSidebar.scoped.css"></style>
