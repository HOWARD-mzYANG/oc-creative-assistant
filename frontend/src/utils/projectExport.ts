import type { OcExport } from '../api/projectApi'

type OcNode = OcExport['nodes'][number]
type OcEdge = OcExport['edges'][number]

const RELATION_LABEL: Record<string, string> = {
    develops_into: '发展为',
    causes: '导致',
    belongs_to: '归属',
    conflicts_with: '冲突',
    references: '引用',
    relates_to: '相关',
}

/** 执行 byOrder 对应的工具转换或计算。 */
const byOrder = (a: OcNode, b: OcNode) => a.sort_order - b.sort_order

/** 执行 esc 对应的工具转换或计算。 */
function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** 执行 fieldsHtml 对应的工具转换或计算。 */
function fieldsHtml(node: OcNode): string {
  const fields = node.meta?.fields
  if (!fields || Object.keys(fields).length === 0) return ''
  const rows = Object.entries(fields)
    .map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`)
    .join('')
  return `<table class="fields">${rows}</table>`
}

/** 执行 contentHtml 对应的工具转换或计算。 */
function contentHtml(node: OcNode): string {
  return node.content ? `<div class="content">${esc(node.content)}</div>` : ''
}

/** 执行 tagsHtml 对应的工具转换或计算。 */
function tagsHtml(node: OcNode): string {
  const tags = node.meta?.tags
  if (!tags || tags.length === 0) return ''
  return `<div class="tags">${tags.map((t) => `<span>${esc(t)}</span>`).join('')}</div>`
}

/** 执行 storySection 对应的工具转换或计算。 */
function storySection(nodes: OcNode[], edges: OcEdge[]): string {
  const plots = nodes.filter((n) => n.node_type === 'plot').sort(byOrder)
  if (plots.length === 0) return ''
  const titleById = new Map(nodes.map((n) => [n.id, n.title]))
  const relBySrc = new Map<string, OcEdge[]>()
  for (const e of edges) {
    if (e.relation_type === 'belongs_to') continue
    if (!relBySrc.has(e.source)) relBySrc.set(e.source, [])
    relBySrc.get(e.source)!.push(e)
  }
  const items = plots
    .map((n) => {
      const rels = (relBySrc.get(n.id) || [])
        .map((e) => {
          const tgt = titleById.get(e.target) || '?'
          const label = e.label || RELATION_LABEL[e.relation_type] || e.relation_type
          return `<li>→ ${esc(tgt)} <em>(${esc(label)})</em></li>`
        })
        .join('')
      const relBlock = rels ? `<ul class="relations">${rels}</ul>` : ''
      return `<section class="node"><h3>${esc(n.title)}</h3>${fieldsHtml(n)}${contentHtml(n)}${relBlock}${tagsHtml(n)}</section>`
    })
    .join('')
  return `<h2 class="board">故事</h2>${items}`
}

/** 执行 charactersSection 对应的工具转换或计算。 */
function charactersSection(nodes: OcNode[]): string {
  const chars = nodes.filter((n) => n.node_type === 'character').sort(byOrder)
  if (chars.length === 0) return ''
  const items = chars
    .map(
      (n) =>
        `<section class="node"><h3>${esc(n.title)}</h3>${fieldsHtml(n)}${contentHtml(n)}${tagsHtml(n)}</section>`,
    )
    .join('')
  return `<h2 class="board">角色</h2>${items}`
}

/** 执行 worldSection 对应的工具转换或计算。 */
function worldSection(nodes: OcNode[], edges: OcEdge[]): string {
  const worlds = nodes.filter((n) => n.node_type === 'worldbuilding')
  if (worlds.length === 0) return ''
  const worldIds = new Set(worlds.map((n) => n.id))
  const parentByChild = new Map<string, string>()
  for (const e of edges) {
    if (e.relation_type === 'belongs_to') parentByChild.set(e.source, e.target)
  }
  const childrenByParent = new Map<string | null, OcNode[]>()
  for (const n of worlds) {
    const p = parentByChild.get(n.id)
    const key = p && worldIds.has(p) ? p : null
    if (!childrenByParent.has(key)) childrenByParent.set(key, [])
    childrenByParent.get(key)!.push(n)
  }
  for (const arr of childrenByParent.values()) arr.sort(byOrder)

  /** 执行 walk 对应的工具转换或计算。 */
  function walk(parentKey: string | null, depth: number): string {
    const children = childrenByParent.get(parentKey) || []
    return children
      .map(
        (n) =>
          `<section class="node world" style="margin-left:${depth * 20}px">
             <h3 class="world-title">${esc(n.title)}</h3>
             ${fieldsHtml(n)}${contentHtml(n)}
           </section>${walk(n.id, depth + 1)}`,
      )
      .join('')
  }
  return `<h2 class="board">世界观</h2>${walk(null, 0)}`
}

const CSS = `
  * { box-sizing: border-box; }
  body {
    font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
    color: #1f2937; line-height: 1.7; margin: 0; padding: 32px 40px;
  }
  .doc-head h1 { font-size: 28px; margin: 0 0 4px; }
  .doc-head p { color: #6b7280; margin: 0 0 8px; }
  h2.board {
    font-size: 20px; margin: 28px 0 12px; padding-bottom: 6px;
    border-bottom: 2px solid #8b5cf6; color: #6d28d9;
    page-break-after: avoid;
  }
  .node {
    margin: 0 0 14px; padding: 12px 16px;
    border: 1px solid #e5e7eb; border-radius: 8px;
    page-break-inside: avoid;
  }
  .node h3 { font-size: 16px; margin: 0 0 8px; }
  .world-title { color: #b45309; }
  .content { white-space: pre-wrap; margin: 6px 0; }
  table.fields { border-collapse: collapse; margin: 6px 0; }
  table.fields th, table.fields td {
    border: 1px solid #e5e7eb; padding: 3px 10px; font-size: 13px; text-align: left;
  }
  table.fields th { background: #f9fafb; color: #6b7280; white-space: nowrap; }
  ul.relations { margin: 6px 0; padding-left: 18px; color: #4b5563; font-size: 14px; }
  .tags { margin-top: 8px; }
  .tags span {
    display: inline-block; font-size: 12px; padding: 2px 8px; margin-right: 6px;
    border-radius: 999px; background: #ede9fe; color: #6d28d9;
  }
  @media print { body { padding: 0; } }
`

type BuildProjectHtmlOptions = {
  autoPrint?: boolean
}

/** 根据项目快照构建可打印 HTML 文档。 */
export function buildProjectHtml(data: OcExport, options: BuildProjectHtmlOptions = {}): string {
  const { project, nodes, edges } = data
  const autoPrint = options.autoPrint ?? true
  const body = [
    `<header class="doc-head"><h1>${esc(project.name)}</h1>${
      project.description ? `<p>${esc(project.description)}</p>` : ''
    }</header>`,
    storySection(nodes, edges),
    charactersSection(nodes),
    worldSection(nodes, edges),
  ].join('')
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>${esc(
    project.name,
  )}</title><style>${CSS}</style></head><body>${body}${
    autoPrint ? '<script>window.onload=function(){setTimeout(function(){window.print()},300)}<\/script>' : ''
  }</body></html>`
}

/** 将项目导出为 PDF；可用时优先使用 Electron 原生 PDF 写入能力。 */
export async function openProjectPdf(data: OcExport): Promise<void> {
  if (window.ocDesktop?.exportProjectPdf) {
    await window.ocDesktop.exportProjectPdf({
      html: buildProjectHtml(data, { autoPrint: false }),
      defaultFileName: `${data.project.name || 'project'}.pdf`,
    })
    return
  }

  const win = window.open('', '_blank')
  if (!win) {
    window.alert('请允许弹出窗口以导出 PDF')
    return
  }
  win.document.open()
  win.document.write(buildProjectHtml(data))
  win.document.close()
}
