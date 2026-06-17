import { onBeforeUnmount, ref } from 'vue'

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

/**
 * 工作区侧边栏的横向拖拽缩放。
 * mousedown 时挂载 document 级监听，并在 mouseup 时清理。
 */
export function usePanelResize(options: {
  min: number
  max: number
  getWidth: () => number
  setWidth: (width: number) => void
  /** 向右拖动会增宽时为 +1；向右拖动会变窄时为 -1。 */
  direction: 1 | -1
}) {
  const isDragging = ref(false)
  let removeListeners: (() => void) | null = null

  function stopDrag() {
    isDragging.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    removeListeners?.()
    removeListeners = null
  }

  function startDrag(event: MouseEvent) {
    event.preventDefault()
    isDragging.value = true
    const startX = event.clientX
    const startWidth = options.getWidth()

    const onMove = (moveEvent: MouseEvent) => {
      const delta = (moveEvent.clientX - startX) * options.direction
      options.setWidth(clamp(startWidth + delta, options.min, options.max))
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', stopDrag, { once: true })
    removeListeners = () => {
      document.removeEventListener('mousemove', onMove)
    }
  }

  onBeforeUnmount(stopDrag)

  return { isDragging, startDrag, stopDrag }
}
