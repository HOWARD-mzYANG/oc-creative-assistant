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
    /** 封装 register 对应的组合式状态和操作。 */
    register(fn) {
      refreshFn = fn
    },
    /** 封装 trigger 对应的组合式状态和操作。 */
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

  /** 封装 setCanvasFocus 对应的组合式状态和操作。 */
  function setCanvasFocus(refs: CanvasFocusRef[]) {
    canvasFocusRefs.value = refs
    selectedNodeIds.value = refs.map((ref) => ref.id)
  }

  /** 封装 clearCanvasFocus 对应的组合式状态和操作。 */
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

/** 封装 injectWorkspaceSelectedNodeIds 对应的组合式状态和操作。 */
export function injectWorkspaceSelectedNodeIds() {
  return inject(WORKSPACE_SELECTED_NODE_IDS_KEY, ref<string[]>([]))
}

/** 封装 injectWorkspaceCanvasFocus 对应的组合式状态和操作。 */
export function injectWorkspaceCanvasFocus() {
  return inject(WORKSPACE_CANVAS_FOCUS_KEY, ref<CanvasFocusRef[]>([]))
}

/** 封装 injectSetCanvasFocus 对应的组合式状态和操作。 */
export function injectSetCanvasFocus() {
  const focus = inject(WORKSPACE_CANVAS_FOCUS_KEY, null)
  const selected = inject(WORKSPACE_SELECTED_NODE_IDS_KEY, null)
  return {
    /** 封装 setCanvasFocus 对应的组合式状态和操作。 */
    setCanvasFocus(refs: CanvasFocusRef[]) {
      if (focus) focus.value = refs
      if (selected) selected.value = refs.map((ref) => ref.id)
    },
    /** 封装 clearCanvasFocus 对应的组合式状态和操作。 */
    clearCanvasFocus() {
      if (focus) focus.value = []
      if (selected) selected.value = []
    },
  }
}

/** 封装 injectWorkspaceGraphRefresh 对应的组合式状态和操作。 */
export function injectWorkspaceGraphRefresh() {
  return inject(WORKSPACE_GRAPH_REFRESH_KEY, null)
}
