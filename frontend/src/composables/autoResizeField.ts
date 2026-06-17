/** 根据内容自动撑高 textarea。 */
export function autoResizeTextarea(el: HTMLTextAreaElement | null | undefined) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

/** 根据文本自动撑宽 input；最大宽度由父容器限制。 */
export function autoResizeInput(el: HTMLInputElement | null | undefined) {
  if (!el) return
  el.style.width = '0'
  el.style.width = `${el.scrollWidth}px`
}
