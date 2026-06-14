<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '../../stores/useProjectStore'
import { updateProject } from '../../api/projectApi'

/**
 * 概览: wallpaper cover, world-doc style fields, debounced auto-save.
 */
const projectStore = useProjectStore()
const { detail } = storeToRefs(projectStore)

const MAX_COVER_EDGE = 1280
const SAVE_DEBOUNCE_MS = 500

const name = ref('')
const description = ref('')
const cover = ref('')
const coverDirty = ref(false)
const saveState = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const isHydrating = ref(true)

let saveTimer: ReturnType<typeof setTimeout> | null = null
let isSaving = false
let saveQueued = false

watch(
  detail,
  (value) => {
    isHydrating.value = true
    name.value = value?.name ?? ''
    description.value = value?.description ?? ''
    cover.value = value?.cover_image ?? ''
    coverDirty.value = false
    void nextTick(() => {
      isHydrating.value = false
    })
  },
  { immediate: true },
)

function fileToScaledDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Could not read the image file'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('Could not decode the image'))
      img.onload = () => {
        const scale = Math.min(1, MAX_COVER_EDGE / Math.max(img.width, img.height))
        const width = Math.max(1, Math.round(img.width * scale))
        const height = Math.max(1, Math.round(img.height * scale))
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('Canvas is not available'))
          return
        }
        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', 0.82))
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
  })
}

function scheduleSave() {
  if (!detail.value || !name.value.trim() || isHydrating.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    void persist()
  }, SAVE_DEBOUNCE_MS)
}

async function persist() {
  if (!detail.value || !name.value.trim()) return
  if (isSaving) {
    saveQueued = true
    return
  }

  isSaving = true
  saveState.value = '保存中…'
  try {
    await updateProject(detail.value.id, {
      name: name.value.trim(),
      description: description.value,
      ...(coverDirty.value ? { cover_image: cover.value } : {}),
    })
    await projectStore.loadProject(detail.value.id, true)
    coverDirty.value = false
    saveState.value = '已保存'
  } catch (error) {
    saveState.value = error instanceof Error ? `保存失败: ${error.message}` : '保存失败'
  } finally {
    isSaving = false
    if (saveQueued) {
      saveQueued = false
      void persist()
    }
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    saveState.value = '请选择图片文件'
    return
  }
  try {
    cover.value = await fileToScaledDataUrl(file)
    coverDirty.value = true
    saveState.value = ''
    await persist()
  } catch (error) {
    saveState.value = error instanceof Error ? error.message : '图片加载失败'
  }
}

function openCoverPicker() {
  fileInput.value?.click()
}

watch([name, description], () => {
  scheduleSave()
})

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<template>
  <section class="overview">
    <button
      type="button"
      class="overview__hero"
      :class="{ 'has-cover': cover }"
      :aria-label="cover ? '双击更换封面图' : '双击添加封面图'"
      @dblclick.stop.prevent="openCoverPicker"
    >
      <div
        class="overview__hero-image"
        :style="cover ? { backgroundImage: `url(${cover})` } : undefined"
      />
      <div class="overview__hero-fade" aria-hidden="true" />
      <span class="overview__hero-hint">
        {{ cover ? '双击更换封面' : '双击添加封面' }}
      </span>
    </button>

    <input
      ref="fileInput"
      class="overview__file-input"
      type="file"
      accept="image/*"
      @change="handleFileChange"
    />

    <div class="overview__surface">
      <header class="overview__head">
        <h2 class="overview__title">概览</h2>
        <span v-if="saveState" class="overview__state">{{ saveState }}</span>
      </header>

      <label class="overview__block">
        <span class="overview__label">项目名称</span>
        <input
          v-model="name"
          class="overview__name"
          type="text"
          placeholder="未命名项目"
          spellcheck="false"
          @blur="scheduleSave"
        />
      </label>

      <label class="overview__block">
        <span class="overview__label">描述</span>
        <textarea
          v-model="description"
          class="overview__description"
          rows="6"
          placeholder="描述这个项目的世界、基调和目标…"
          spellcheck="true"
          @blur="scheduleSave"
        />
      </label>
    </div>
  </section>
</template>

<style scoped>
.overview {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--paper);
}

.overview__hero {
  position: relative;
  flex-shrink: 0;
  width: 100%;
  height: clamp(180px, 28vh, 300px);
  margin: 0;
  padding: 0;
  border: none;
  background:
    radial-gradient(circle at 18% 20%, rgba(233, 130, 74, 0.14), transparent 52%),
    linear-gradient(120deg, #faf8f5 0%, #f3f1f8 100%);
  cursor: pointer;
  overflow: hidden;
}

.overview__hero.has-cover {
  background: #e8e4df;
}

.overview__hero-image {
  position: absolute;
  inset: 0;
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
}

.overview__hero-fade {
  position: absolute;
  inset: auto 0 0;
  height: 62%;
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0.55) 42%,
    var(--paper) 100%
  );
  pointer-events: none;
}

.overview__hero-hint {
  position: absolute;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-soft);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(28, 25, 23, 0.08);
  opacity: 0;
  transition: opacity 0.16s ease;
  pointer-events: none;
}

.overview__hero:hover .overview__hero-hint,
.overview__hero:focus-visible .overview__hero-hint {
  opacity: 1;
}

.overview__file-input {
  display: none;
}

.overview__surface {
  flex: 1;
  min-height: 0;
  padding: 8px 28px 28px 44px;
  position: relative;
  background: var(--paper);
  background-image:
    linear-gradient(var(--paper), var(--paper)),
    repeating-linear-gradient(
      to bottom,
      transparent 0,
      transparent 33px,
      rgba(28, 25, 23, 0.04) 33px,
      rgba(28, 25, 23, 0.04) 34px
    );
}

.overview__surface::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 28px;
  width: 1px;
  background: rgba(233, 130, 74, 0.22);
  pointer-events: none;
}

.overview__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}

.overview__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.75rem;
  font-weight: 600;
  line-height: 1.25;
  color: var(--text);
}

.overview__state {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--muted);
}

.overview__block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 28px;
}

.overview__label {
  font-family: var(--font-ui);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.overview__name {
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text);
}

.overview__name:focus {
  outline: none;
}

.overview__description {
  width: 100%;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--text-soft);
  resize: vertical;
  min-height: 8rem;
}

.overview__description:focus {
  outline: none;
  color: var(--text);
}
</style>
