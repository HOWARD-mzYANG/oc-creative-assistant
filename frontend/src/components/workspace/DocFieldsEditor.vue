<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { autoResizeInput, autoResizeTextarea } from '../../composables/autoResizeField'

/** 无边框键值字段块（世界笔记和角色属性共用）。 */
export interface DocFieldRow {
  key: string
  value: string
}

const rows = defineModel<DocFieldRow[]>({ required: true })

const emit = defineEmits<{ blur: [] }>()

const valueEls = new Map<number, HTMLTextAreaElement>()
const nameEls = new Map<number, HTMLInputElement>()

function setValueRef(index: number, el: unknown) {
  if (el instanceof HTMLTextAreaElement) valueEls.set(index, el)
  else valueEls.delete(index)
}

function setNameRef(index: number, el: unknown) {
  if (el instanceof HTMLInputElement) nameEls.set(index, el)
  else nameEls.delete(index)
}

async function resizeAll() {
  await nextTick()
  nameEls.forEach(autoResizeInput)
  valueEls.forEach(autoResizeTextarea)
}

function onNameInput(event: Event) {
  autoResizeInput(event.target as HTMLInputElement)
}

function onValueInput(event: Event) {
  autoResizeTextarea(event.target as HTMLTextAreaElement)
}

function addField() {
  rows.value.push({ key: '', value: '' })
  void resizeAll()
}

function onBlur() {
  emit('blur')
}

onMounted(() => {
  void resizeAll()
})

watch(rows, () => {
  void resizeAll()
}, { deep: true })
</script>

<template>
  <div class="doc-fields">
    <section
      v-for="(row, index) in rows"
      :key="index"
      class="doc-fields__block"
    >
      <input
        :ref="(el) => setNameRef(index, el)"
        v-model="row.key"
        class="doc-fields__name"
        type="text"
        placeholder="字段名称"
        spellcheck="false"
        @input="onNameInput"
        @blur="onBlur"
      />
      <textarea
        :ref="(el) => setValueRef(index, el)"
        v-model="row.value"
        class="doc-fields__value"
        rows="1"
        placeholder="填写内容…"
        spellcheck="true"
        @input="onValueInput"
        @blur="onBlur"
      />
    </section>

    <button type="button" class="doc-fields__add" @click="addField">
      + 添加字段
    </button>
  </div>
</template>

<style scoped>
.doc-fields {
  display: flex;
  flex-direction: column;
  gap: 28px;
  width: 100%;
}

.doc-fields__block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.doc-fields__name {
  width: auto;
  max-width: 100%;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 0;
  field-sizing: content;
}

.doc-fields__name:focus {
  outline: none;
  color: var(--text-soft);
}

.doc-fields__name::placeholder {
  color: rgba(138, 133, 125, 0.65);
  text-transform: none;
  letter-spacing: 0.02em;
  font-weight: 500;
}

.doc-fields__value {
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--text-soft);
  resize: none;
  overflow: hidden;
  min-height: 1.65em;
}

.doc-fields__value:focus {
  outline: none;
  color: var(--text);
}

.doc-fields__add {
  align-self: flex-start;
  border: none;
  background: none;
  padding: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-deep);
  cursor: pointer;
}

.doc-fields__add:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
