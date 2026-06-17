import { inject, provide, ref, type InjectionKey, type Ref } from 'vue'

export interface CanvasFocusRef {
  id: string
  type: string
  title: string
}

export const WORKSPACE_SELECTED_NODE_IDS_KEY: InjectionKey<Ref<string[]>> = Symbol(
  'workspaceSelectedNodeIds',
)

export const WORKSPACE_CANVAS_FOCUS_KEY: InjectionKey<Ref<CanvasFocusRef[]>> = Symbol(
  'workspaceCanvasFocus',
)

type GraphRefreshRegistry = {
  register: (fn: () => void | Promise<void>) => void
  trigger: () => Promise<void>
}

export const WORKSPACE_GRAPH_REFRESH_KEY: InjectionKey<GraphRefreshRegistry> = Symbol(
  'workspaceGraphRefresh',
)

/** 由 WorkspaceShell 提供：画布视图发布焦点，BottomComposer 合并进智能体上下文。 */
export function provideWorkspaceChatContext() {
  const selectedNodeIds = ref<string[]>([])
  const canvasFocusRefs = ref<CanvasFocusRef[]>([])

  const graphRefreshRegistry: GraphRefreshRegistry = {
    register(fn) {
      refreshFn = fn
    },
    async trigger() {
      if (refreshFn) {
        await refreshFn()
      }
    },
  }

  let refreshFn: (() => void | Promise<void>) | null = null

  provide(WORKSPACE_SELECTED_NODE_IDS_KEY, selectedNodeIds)
  provide(WORKSPACE_CANVAS_FOCUS_KEY, canvasFocusRefs)
  provide(WORKSPACE_GRAPH_REFRESH_KEY, graphRefreshRegistry)

  function setCanvasFocus(refs: CanvasFocusRef[]) {
    canvasFocusRefs.value = refs
    selectedNodeIds.value = refs.map((ref) => ref.id)
  }

  function clearCanvasFocus() {
    canvasFocusRefs.value = []
    selectedNodeIds.value = []
  }

  return {
    selectedNodeIds,
    canvasFocusRefs,
    setCanvasFocus,
    clearCanvasFocus,
    triggerGraphRefresh: () => graphRefreshRegistry.trigger(),
  }
}

export function injectWorkspaceSelectedNodeIds() {
  return inject(WORKSPACE_SELECTED_NODE_IDS_KEY, ref<string[]>([]))
}

export function injectWorkspaceCanvasFocus() {
  return inject(WORKSPACE_CANVAS_FOCUS_KEY, ref<CanvasFocusRef[]>([]))
}

export function injectSetCanvasFocus() {
  const focus = inject(WORKSPACE_CANVAS_FOCUS_KEY, null)
  const selected = inject(WORKSPACE_SELECTED_NODE_IDS_KEY, null)
  return {
    setCanvasFocus(refs: CanvasFocusRef[]) {
      if (focus) focus.value = refs
      if (selected) selected.value = refs.map((ref) => ref.id)
    },
    clearCanvasFocus() {
      if (focus) focus.value = []
      if (selected) selected.value = []
    },
  }
}

export function injectWorkspaceGraphRefresh() {
  return inject(WORKSPACE_GRAPH_REFRESH_KEY, null)
}
