<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  RELATION_TYPE_OPTIONS,
  type CreativeFlowEdge,
  type CreativeFlowNode,
  type CreativeRelationType,
} from '../../types/node'

/**
 * 边详情面板。
 *
 * 提供方向反转、关系类型切换和标签编辑；节点查找只用于展示源/目标标题。
 * 实际边数据持久化由父组件在收到 emit('edge-updated') 后处理。
 */
const props = defineProps<{
  selectedEdge: CreativeFlowEdge
  nodes: CreativeFlowNode[]
}>()

const emit = defineEmits<{
  'edge-updated': [edge: CreativeFlowEdge]
  'edge-deleted': [edgeId: string]
}>()

const isEdgeRelationSelectOpen = ref(false)

/** 关闭目标视图或弹层。 */
function closeAllSelects(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.custom-select-container')) {
    isEdgeRelationSelectOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', closeAllSelects)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAllSelects)
})

const sourceNodeTitle = computed(
  () => props.nodes.find((node) => node.id === props.selectedEdge.source)?.data.title ?? props.selectedEdge.source,
)

const targetNodeTitle = computed(
  () => props.nodes.find((node) => node.id === props.selectedEdge.target)?.data.title ?? props.selectedEdge.target,
)

/** 获取指定数据或派生状态。 */
function getRelationLabel(relationType: CreativeRelationType) {
  return RELATION_TYPE_OPTIONS.find((option) => option.value === relationType)?.label ?? '相关'
}

/** 更新指定业务对象并同步相关视图。 */
function updateEdge(partial: Partial<CreativeFlowEdge['data']>) {
  const data = {
    ...props.selectedEdge.data,
    ...partial,
  }

  emit('edge-updated', {
    ...props.selectedEdge,
    label: data.label,
    data,
  })
}

/** 更新指定业务对象并同步相关视图。 */
function updateEdgeRelation(relationType: CreativeRelationType) {
  updateEdge({
    relationType,
    label: getRelationLabel(relationType),
  })
}

/** 说明 reverseSelectedEdge 的局部业务逻辑。 */
function reverseSelectedEdge() {
  emit('edge-updated', {
    ...props.selectedEdge,
    source: props.selectedEdge.target,
    target: props.selectedEdge.source,
    sourceHandle: props.selectedEdge.targetHandle,
    targetHandle: props.selectedEdge.sourceHandle,
  })
}
</script>

<template>
  <div class="edge-detail-panel">
    <section class="detail-header">
      <p>当前边</p>
      <h2>{{ selectedEdge.data.label }}</h2>
    </section>

    <section class="detail-panel">
      <dl class="edge-meta">
        <div>
          <dt>源节点</dt>
          <dd>{{ sourceNodeTitle }}</dd>
        </div>
        <div>
          <dt>目标节点</dt>
          <dd>{{ targetNodeTitle }}</dd>
        </div>
      </dl>

      <label for="edge-relation">关系类型</label>
      <div class="custom-select-container">
        <div
          class="custom-select-trigger"
          :class="{ 'is-open': isEdgeRelationSelectOpen }"
          @click="isEdgeRelationSelectOpen = !isEdgeRelationSelectOpen"
        >
          <span>{{ getRelationLabel(selectedEdge.data.relationType) }}</span>
          <div class="custom-select-arrow"></div>
        </div>
        <ul class="custom-select-options" v-show="isEdgeRelationSelectOpen">
          <li
            v-for="option in RELATION_TYPE_OPTIONS"
            :key="option.value"
            class="custom-select-option"
            :class="{ 'is-selected': selectedEdge.data.relationType === option.value }"
            @click="updateEdgeRelation(option.value as CreativeRelationType); isEdgeRelationSelectOpen = false"
          >
            {{ option.label }}
          </li>
        </ul>
      </div>

      <label for="edge-label">边标签</label>
      <div class="input-wrapper">
        <input
          id="edge-label"
          type="text"
          :value="selectedEdge.data.label"
          @input="updateEdge({ label: ($event.target as HTMLInputElement).value })"
        />
      </div>

      <button type="button" class="secondary-action" @click="reverseSelectedEdge">反转方向</button>
      <button type="button" class="danger" @click="emit('edge-deleted', selectedEdge.id)">删除边</button>
    </section>
  </div>
</template>

<style scoped src="./AgentSidebar.scoped.css"></style>
