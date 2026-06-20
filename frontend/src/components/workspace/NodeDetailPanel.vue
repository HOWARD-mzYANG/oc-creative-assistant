<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { loadRagContext, type RagContextResponseDto } from '../../api/graphApi'
import type { CreativeFlowNode, CreativeNodeData } from '../../types/node'

/**
 * 节点详情面板。
 *
 * 同时承载节点字段编辑、智能体 mock 占位和 RAG 调试视图；三者都只有在“选中单个节点”时才有意义，
 * 因此合并在同一个子组件里。切换节点时会通过 watch(props.selectedNode.id) 清空临时预览。
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

/* 自定义下拉框没有使用原生 select，因此组件需要自行跟踪展开状态，并在外部点击时收起。 */
const isNodeStatusSelectOpen = ref(false)

/** 关闭目标视图或弹层。 */
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

/** 更新指定业务对象并同步相关视图。 */
function updateNodeData(partial: Partial<CreativeNodeData>) {
  emit('node-updated', {
    ...props.selectedNode,
    data: {
      ...props.selectedNode.data,
      ...partial,
    },
  })
}

/** 更新指定业务对象并同步相关视图。 */
function updateNodeTags(rawValue: string) {
  const tags = rawValue
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
  updateNodeData({ tags })
}

/** 处理对应的用户交互或组件事件。 */
function handleDeleteNode() {
  emit('node-deleted', props.selectedNode.id)
}

/**
 * 生成占位智能体结果。
 *
 * 当前 mock 只用于确认侧栏交互和结果展示；不会自动写入节点正文，
 * 保留“用户手动采纳生成内容”的产品边界。
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
      status: '结构智能体尚未连接',
    },
    null,
    2,
  )
}

/** 说明 summarizeContent 的局部业务逻辑。 */
function summarizeContent(content: string) {
  return content.length > 120 ? `${content.slice(0, 120)}...` : content
}

/**
 * 加载当前节点的 RAG 调试上下文。
 *
 * 只展示后端返回的图关系、向量上下文和最终 prompt；不会调用 LLM，
 * 也不会把结果写回节点正文。
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

/* 切换节点时清空临时预览，避免把上一个节点的智能体 / RAG 结果误认为当前上下文。 */
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
      <h3>智能体操作占位</h3>
      <div class="agent-actions">
        <button type="button" @click="runAgentMock('inspiration')">灵感</button>
        <button type="button" @click="runAgentMock('research')">资料</button>
        <button type="button" @click="runAgentMock('structure')">结构</button>
      </div>
      <pre v-if="agentResult" class="agent-result">{{ agentResult }}</pre>
    </section>

    <section class="detail-panel rag-panel">
      <h3>RAG / 智能体调试</h3>
      <label for="rag-query">用户请求</label>
      <div class="input-wrapper">
        <textarea
          id="rag-query"
          rows="3"
          v-model="ragQuery"
          placeholder="留空则使用当前节点标题和正文作为检索问题"
        />
      </div>
      <!-- 该按钮只查看上下文，不调用 LLM，也不会把结果写入节点正文。 -->
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
            <strong>分数 {{ item.score.toFixed(2) }}</strong>
            <span>{{ item.type }} · {{ item.title }}</span>
            <p>{{ summarizeContent(item.content) }}</p>
          </article>
          <p class="rag-debug-line">
            向量库: {{ ragResult.debug.vector_store }}
            <span v-if="ragResult.debug.vector_error"> / {{ ragResult.debug.vector_error }}</span>
          </p>
        </details>

        <details>
          <summary>最终提示词</summary>
          <!-- 先展示 AI 将收到的上下文，便于确认检索与组装是否合理。 -->
          <pre class="prompt-preview">{{ ragResult.prompt }}</pre>
        </details>
      </div>
    </section>
  </div>
</template>

<style scoped src="./AgentSidebar.scoped.css"></style>
