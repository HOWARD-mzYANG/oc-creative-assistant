<script setup lang="ts">
import { nextTick, ref } from 'vue'

/**
 * 通用行内文本编辑组件。
 *
 * 默认展示普通文本；点击进入编辑模式：Enter / blur 保存，Esc 取消。
 * 编辑态和展示态都带 `nodrag nopan`，避免 Vue Flow 截获鼠标事件导致拖拽冲突。
 */
const props = defineProps<{
  modelValue: string
  placeholder?: string
  multiline?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [string]
  save: [string]
}>()

const editing = ref(false)
const draft = ref('')
const inputEl = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)

/** 说明 enterEdit 的局部业务逻辑。 */
async function enterEdit() {
  draft.value = props.modelValue
  editing.value = true
  await nextTick()
  inputEl.value?.focus()
  if (inputEl.value instanceof HTMLInputElement) inputEl.value.select()
}

/** 保存当前编辑内容到后端或缓存。 */
function save() {
  if (!editing.value) return
  editing.value = false
  if (draft.value !== props.modelValue) {
    emit('update:modelValue', draft.value)
    emit('save', draft.value)
  }
}

/** 取消当前临时编辑状态。 */
function cancel() {
  draft.value = props.modelValue
  editing.value = false
}
</script>

<template>
  <span
    v-if="!editing"
    class="inline-text nodrag nopan"
    :class="{ 'inline-text--empty': !modelValue }"
    @click.stop="enterEdit"
  >{{ modelValue || placeholder || '点击编辑' }}</span>

  <textarea
    v-else-if="multiline"
    ref="inputEl"
    v-model="draft"
    class="inline-input nodrag nopan"
    rows="3"
    @keydown.enter.prevent="save"
    @keydown.esc.prevent="cancel"
    @blur="save"
    @click.stop
  ></textarea>

  <input
    v-else
    ref="inputEl"
    v-model="draft"
    class="inline-input nodrag nopan"
    @keydown.enter.prevent="save"
    @keydown.esc.prevent="cancel"
    @blur="save"
    @click.stop
  />
</template>

<style scoped>
.inline-text {
  cursor: text;
  border-radius: 4px;
  transition: background 0.12s;
}
.inline-text:hover {
  background: rgba(99, 102, 241, 0.1);
}
.inline-text--empty {
  color: #9ca3af;
}
.inline-input {
  width: 100%;
  box-sizing: border-box;
  padding: 2px 4px;
  border: 1px solid var(--accent);
  border-radius: 4px;
  font: inherit;
  color: inherit;
  background: #fff;
  resize: vertical;
}
</style>
