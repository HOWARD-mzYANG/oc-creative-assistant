<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../../stores/useChatStore'

const chat = useChatStore()
const { sessions, sessionId } = storeToRefs(chat)

const menuOpenId = ref<string | null>(null)
const menuPos = ref({ top: 0, left: 0 })
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const editInput = ref<HTMLInputElement | null>(null)

function toggleMenu(id: string, event: MouseEvent) {
  if (menuOpenId.value === id) {
    menuOpenId.value = null
    return
  }
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  menuPos.value = { top: rect.bottom + 4, left: rect.left }
  menuOpenId.value = id
}

function closeMenu() {
  menuOpenId.value = null
}

async function startRename(s: { id: string; title: string }) {
  closeMenu()
  editingId.value = s.id
  editingTitle.value = s.title
  await nextTick()
  editInput.value?.focus()
  editInput.value?.select()
}

function commitRename() {
  const id = editingId.value
  if (!id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  const current = sessions.value.find((s) => s.id === id)
  if (title && title !== current?.title) void chat.renameSession(id, title)
}

function cancelRename() {
  editingId.value = null
}

function onTitleClick(s: { id: string; title: string }) {
  if (s.id === sessionId.value) startRename(s)
  else void chat.switchSession(s.id)
}

function onNewChat() {
  void chat.newSession()
}

async function onDeleteSession(id: string) {
  closeMenu()
  if (!window.confirm('删除这段对话及其历史记录吗？')) return
  await chat.deleteSession(id)
}
</script>

<template>
  <aside class="chat-sessions">
    <div class="chat-sessions__head">
      <span>对话</span>
      <button type="button" class="chat-sessions__new" title="新对话" @click="onNewChat">+</button>
    </div>

    <div class="chat-sessions__list">
      <div
        v-for="s in sessions"
        :key="s.id"
        class="chat-sessions__item"
        :class="{ 'is-active': s.id === sessionId }"
      >
        <input
          v-if="editingId === s.id"
          ref="editInput"
          v-model="editingTitle"
          class="chat-sessions__edit"
          @keyup.enter="commitRename"
          @keyup.esc="cancelRename"
          @blur="commitRename"
        />
        <button
          v-else
          type="button"
          class="chat-sessions__title"
          :title="s.id === sessionId ? '点击重命名' : '打开对话'"
          @click="onTitleClick(s)"
        >
          {{ s.title || '未命名对话' }}
        </button>
        <button
          type="button"
          class="chat-sessions__more"
          title="更多"
          @click.stop="toggleMenu(s.id, $event)"
        >
          ⋯
        </button>
      </div>
    </div>

    <template v-if="menuOpenId">
      <div class="chat-sessions__backdrop" @click="closeMenu" />
      <div
        class="chat-sessions__menu"
        :style="{ top: menuPos.top + 'px', left: menuPos.left + 'px' }"
      >
        <button
          type="button"
          class="chat-sessions__menu-item chat-sessions__menu-item--danger"
          @click.stop="onDeleteSession(menuOpenId)"
        >
          删除
        </button>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.chat-sessions {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border, #e5e7eb);
  background: var(--panel, #fafafa);
}

.chat-sessions__head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.chat-sessions__new {
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.chat-sessions__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-sessions__item {
  display: flex;
  align-items: center;
  border-radius: 8px;
}

.chat-sessions__item:hover {
  background: rgba(124, 92, 255, 0.08);
}

.chat-sessions__item.is-active {
  background: var(--accent-soft, rgba(139, 92, 246, 0.12));
  box-shadow: inset 0 0 0 1.5px var(--accent-border, rgba(139, 92, 246, 0.35));
}

.chat-sessions__title {
  flex: 1;
  min-width: 0;
  text-align: left;
  padding: 8px 10px;
  border: none;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #111);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-sessions__item.is-active .chat-sessions__title {
  color: var(--accent-deep, #6d28d9);
}

.chat-sessions__edit {
  flex: 1;
  min-width: 0;
  margin: 4px 6px;
  padding: 4px 8px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  font-size: 13px;
}

.chat-sessions__more {
  border: none;
  background: transparent;
  color: var(--muted, #999);
  padding: 4px 8px;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
}

.chat-sessions__item:hover .chat-sessions__more,
.chat-sessions__item.is-active .chat-sessions__more {
  opacity: 1;
}

.chat-sessions__backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
}

.chat-sessions__menu {
  position: fixed;
  z-index: 1001;
  min-width: 120px;
  background: #fff;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 4px;
}

.chat-sessions__menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.chat-sessions__menu-item:hover {
  background: #f3f4f6;
}

.chat-sessions__menu-item--danger {
  color: #dc2626;
}
</style>
