/** 旧版项目列表分组 ID，保留给 mock / 兼容代码；左侧主入口已切换为节点工具栏。 */
export type ProjectGroupId = 'ideas' | 'characters' | 'worldbuilding' | 'plot' | 'research' | 'structure'

/** 右侧智能体面板的工作模式。 */
export type AgentMode = 'inspiration' | 'research' | 'structure'

export const AGENT_MODE_LABELS: Record<AgentMode | 'auto', { label: string; hint: string }> = {
  auto: { label: '自动', hint: '智能体会根据你的消息选择资料 / 灵感 / 结构模式' },
  research: { label: '资料', hint: '查询项目里已有的角色、世界观和故事内容' },
  inspiration: { label: '灵感', hint: '发散想法和追问方向，也可能自动捕捉新概念' },
  structure: { label: '结构', hint: '提出新的节点和关系供你确认' },
}

/** 侧边栏、当前节点卡片和智能体面板共享的节点摘要结构。 */
export interface ProjectItem {
  id: string
  title: string
  kind: string
  summary: string
  meta: string
}

/** 左侧项目面板按业务类型组织节点条目。 */
export interface ProjectGroup {
  id: ProjectGroupId
  title: string
  items: ProjectItem[]
}

/** 右侧智能体面板中的建议卡片 */
export interface AgentSuggestion {
  id: string
  title: string
  body: string
}

/** 底部状态栏聚合三类运行状态：保存、索引和模型。 */
export interface WorkspaceStatus {
  saveState: string
  indexState: string
  modelState: string
}
